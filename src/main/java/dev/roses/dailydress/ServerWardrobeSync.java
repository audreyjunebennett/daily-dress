package dev.roses.dailydress;

import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;

import javax.imageio.ImageIO;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Comparator;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Iterator;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;

public final class ServerWardrobeSync implements AutoCloseable {
    private static final DateTimeFormatter BACKUP_TIME = DateTimeFormatter.ofPattern("yyyy-MM-dd_HH-mm-ss");
    private static final long OFFER_LIFETIME_NANOS = 5L * 60L * 1_000_000_000L;

    private final DailyDress owner;
    private final WardrobeService wardrobe;
    private final ConcurrentHashMap<UUID, PendingOffer> pending = new ConcurrentHashMap<>();
    private final Set<UUID> installing = ConcurrentHashMap.newKeySet();
    private final ExecutorService installer = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "Daily Dress wardrobe sync");
        thread.setDaemon(true);
        return thread;
    });

    public ServerWardrobeSync(DailyDress owner, WardrobeService wardrobe) {
        this.owner = owner;
        this.wardrobe = wardrobe;
    }

    public void register() {
        ServerPlayNetworking.registerGlobalReceiver(
                SyncPackets.OfferPayload.TYPE,
                (payload, context) -> context.server().execute(() -> handleOffer(context.player(), payload))
        );
        ServerPlayNetworking.registerGlobalReceiver(
                SyncPackets.ArchivePayload.TYPE,
                (payload, context) -> context.server().execute(() -> handleArchive(context.server(), context.player(), payload))
        );
        ServerPlayConnectionEvents.DISCONNECT.register((handler, server) -> {
            UUID playerId = handler.player.getUUID();
            pending.remove(playerId);
        });
    }

    private void handleOffer(ServerPlayer player, SyncPackets.OfferPayload payload) {
        UUID playerId = player.getUUID();
        if (!owner.config().isEnabled(playerId)) {
            decide(player, payload.hash(), SyncPackets.DECISION_REJECTED, "Daily Dress is not enabled for this player.");
            return;
        }
        if (installing.contains(playerId)) {
            decide(player, payload.hash(), SyncPackets.DECISION_REJECTED, "A wardrobe sync is already being installed.");
            return;
        }
        if (!validHash(payload.hash())
                || payload.fileCount() < 1
                || payload.fileCount() > SyncPackets.MAX_FILES
                || payload.archiveBytes() < 1
                || payload.archiveBytes() > SyncPackets.MAX_ARCHIVE_BYTES) {
            decide(player, payload.hash(), SyncPackets.DECISION_REJECTED, "The wardrobe offer failed its safety limits.");
            return;
        }

        Path personal = wardrobe.personalWardrobe(playerId);
        if (payload.hash().equals(readStoredHash(personal)) && containsPng(personal)) {
            pending.remove(playerId);
            decide(player, payload.hash(), SyncPackets.DECISION_UP_TO_DATE, "Wardrobe already synchronized.");
            return;
        }

        pending.put(playerId, new PendingOffer(
                payload.hash(),
                payload.fileCount(),
                payload.archiveBytes(),
                System.nanoTime()
        ));
        decide(player, payload.hash(), SyncPackets.DECISION_UPLOAD, "Upload requested.");
    }

    private void handleArchive(MinecraftServer server, ServerPlayer player, SyncPackets.ArchivePayload payload) {
        UUID playerId = player.getUUID();
        PendingOffer offer = pending.remove(playerId);
        if (offer == null
                || System.nanoTime() - offer.createdAtNanos > OFFER_LIFETIME_NANOS
                || !offer.hash.equals(payload.hash())
                || offer.archiveBytes != payload.archive().length
                || !validHash(payload.hash())) {
            result(player, payload.hash(), false, "The wardrobe upload did not match its offer. Please try again.");
            return;
        }
        if (!installing.add(playerId)) {
            result(player, payload.hash(), false, "A wardrobe sync is already being installed.");
            return;
        }

        byte[] archive = payload.archive();
        CompletableFuture
                .supplyAsync(() -> {
                    try {
                        return install(playerId, offer, archive);
                    } catch (Exception exception) {
                        throw new RuntimeException(exception);
                    }
                }, installer)
                .whenComplete((installed, error) -> server.execute(() -> {
                    installing.remove(playerId);
                    ServerPlayer current = server.getPlayerList().getPlayer(playerId);
                    if (error != null) {
                        DailyDress.LOGGER.error("Could not synchronize wardrobe for {}", player.getGameProfile().name(), error);
                        if (current != null) result(current, payload.hash(), false, "Roses could not install that wardrobe safely.");
                        return;
                    }
                    DailyDress.LOGGER.info(
                            "Synchronized {} personal Daily Dress skins for {}. Backup: {}",
                            installed.fileCount,
                            player.getGameProfile().name(),
                            installed.backup == null ? "none (first install)" : installed.backup
                    );
                    if (current != null) result(current, payload.hash(), true, "Personal wardrobe synchronized.");
                }));
    }

    private InstallResult install(UUID playerId, PendingOffer offer, byte[] archive) throws IOException {
        if (!sha256(archive).equals(offer.hash)) {
            throw new IOException("archive hash mismatch");
        }

        Path personalRoot = wardrobe.personalWardrobes().toAbsolutePath().normalize();
        Files.createDirectories(personalRoot);
        Path target = personalRoot.resolve(playerId.toString()).normalize();
        if (!target.startsWith(personalRoot)) throw new IOException("personal wardrobe escaped its root");

        String token = UUID.randomUUID().toString();
        Path staging = personalRoot.resolve("." + playerId + "-sync-staging-" + token);
        Path previous = personalRoot.resolve("." + playerId + "-sync-previous-" + token);
        Path backup = null;

        try {
            Files.createDirectories(staging);
            int extracted = extractValidated(archive, staging);
            if (extracted != offer.fileCount) {
                throw new IOException("expected " + offer.fileCount + " skins but received " + extracted);
            }
            Files.writeString(staging.resolve(".daily-dress-sync"), offer.hash + "\n" + extracted + "\n");
            Files.writeString(
                    staging.resolve("THIS IS YOUR PERSONAL DAILY DRESS WARDROBE.txt"),
                    "This folder belongs only to Minecraft player " + playerId + ".\n"
                            + "Daily Dress Skin Styler synchronizes it automatically through Minecraft.\n"
                            + "The server validates every upload and saves the previous folder first.\n"
            );

            if (Files.exists(target)) {
                Path backupRoot = wardrobe.root().resolve("sync-backups").resolve(playerId.toString());
                backup = uniqueBackupPath(backupRoot, BACKUP_TIME.format(LocalDateTime.now()));
                copyTree(target, backup);
                moveDirectory(target, previous);
            }

            try {
                moveDirectory(staging, target);
            } catch (IOException exception) {
                if (Files.exists(previous) && !Files.exists(target)) moveDirectory(previous, target);
                throw exception;
            }

            if (Files.exists(previous)) deleteTree(previous);
            return new InstallResult(extracted, backup);
        } finally {
            if (Files.exists(staging)) deleteTree(staging);
        }
    }

    private int extractValidated(byte[] archive, Path staging) throws IOException {
        int files = 0;
        long uncompressed = 0;
        Set<String> seen = new HashSet<>();
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(archive))) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                if (entry.isDirectory()) continue;
                String rawName = entry.getName().replace('\\', '/');
                Path relative = Path.of(rawName).normalize();
                if (rawName.startsWith("/")
                        || relative.isAbsolute()
                        || relative.startsWith("..")
                        || !rawName.toLowerCase(Locale.ROOT).endsWith(".png")) {
                    throw new IOException("unsafe archive entry " + rawName);
                }
                String key = relative.toString().toLowerCase(Locale.ROOT);
                if (!seen.add(key)) throw new IOException("duplicate archive entry " + rawName);
                if (++files > SyncPackets.MAX_FILES) throw new IOException("too many skins");

                ByteArrayOutputStream output = new ByteArrayOutputStream();
                byte[] buffer = new byte[8192];
                int read;
                while ((read = zip.read(buffer)) != -1) {
                    output.write(buffer, 0, read);
                    if (output.size() > SyncPackets.MAX_FILE_BYTES) throw new IOException(rawName + " is too large");
                }
                byte[] png = output.toByteArray();
                uncompressed += png.length;
                if (uncompressed > SyncPackets.MAX_UNCOMPRESSED_BYTES) throw new IOException("wardrobe expands beyond its safety limit");

                if (!isValidSkinPng(png)) {
                    throw new IOException(rawName + " is not a valid 64x64 PNG skin");
                }
                Path destination = staging.resolve(relative).normalize();
                if (!destination.startsWith(staging)) throw new IOException("archive path escaped staging");
                Files.createDirectories(destination.getParent());
                Files.write(destination, png);
                zip.closeEntry();
            }
        }
        if (files == 0) throw new IOException("wardrobe archive was empty");
        return files;
    }

    private static boolean isValidSkinPng(byte[] png) throws IOException {
        try (ImageInputStream input = ImageIO.createImageInputStream(new ByteArrayInputStream(png))) {
            if (input == null) return false;
            Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) return false;
            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                if (reader.getWidth(0) != 64 || reader.getHeight(0) != 64) return false;
                return reader.read(0) != null;
            } finally {
                reader.dispose();
            }
        }
    }

    private void decide(ServerPlayer player, String hash, int decision, String message) {
        if (ServerPlayNetworking.canSend(player, SyncPackets.DecisionPayload.TYPE)) {
            ServerPlayNetworking.send(player, new SyncPackets.DecisionPayload(hash, decision, message));
        }
    }

    private void result(ServerPlayer player, String hash, boolean success, String message) {
        if (ServerPlayNetworking.canSend(player, SyncPackets.ResultPayload.TYPE)) {
            ServerPlayNetworking.send(player, new SyncPackets.ResultPayload(hash, success, message));
        }
    }

    private static boolean validHash(String hash) {
        return hash != null && hash.matches("[0-9a-f]{64}");
    }

    private static String readStoredHash(Path personal) {
        try {
            Path manifest = personal.resolve(".daily-dress-sync");
            if (!Files.isRegularFile(manifest)) return "";
            String first = Files.readAllLines(manifest).stream().findFirst().orElse("").trim();
            return validHash(first) ? first : "";
        } catch (IOException exception) {
            return "";
        }
    }

    private static boolean containsPng(Path directory) {
        if (!Files.isDirectory(directory)) return false;
        try (var files = Files.walk(directory)) {
            return files.anyMatch(path -> Files.isRegularFile(path)
                    && path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".png"));
        } catch (IOException exception) {
            return false;
        }
    }

    private static String sha256(byte[] bytes) throws IOException {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException exception) {
            throw new IOException("SHA-256 unavailable", exception);
        }
    }

    private static Path uniqueBackupPath(Path root, String base) throws IOException {
        Files.createDirectories(root);
        Path candidate = root.resolve(base);
        int suffix = 2;
        while (Files.exists(candidate)) candidate = root.resolve(base + "-" + suffix++);
        return candidate;
    }

    private static void copyTree(Path source, Path destination) throws IOException {
        try (var paths = Files.walk(source)) {
            for (Path path : paths.toList()) {
                Path target = destination.resolve(source.relativize(path));
                if (Files.isDirectory(path)) {
                    Files.createDirectories(target);
                } else {
                    Files.createDirectories(target.getParent());
                    Files.copy(path, target, StandardCopyOption.COPY_ATTRIBUTES);
                }
            }
        }
    }

    private static void moveDirectory(Path source, Path destination) throws IOException {
        try {
            Files.move(source, destination, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException exception) {
            Files.move(source, destination);
        }
    }

    private static void deleteTree(Path root) throws IOException {
        if (!Files.exists(root)) return;
        try (var paths = Files.walk(root)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
        }
    }

    @Override
    public void close() {
        pending.clear();
        installer.shutdownNow();
    }

    private record PendingOffer(String hash, int fileCount, int archiveBytes, long createdAtNanos) {}
    private record InstallResult(int fileCount, Path backup) {}
}
