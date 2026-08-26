package dev.roses.dailydress.client;

import dev.roses.dailydress.DailyDress;
import dev.roses.dailydress.SyncPackets;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

public final class ClientWardrobeSync {
    private final Path outbox = FabricLoader.getInstance().getConfigDir()
            .resolve("daily-dress")
            .resolve("sync-outbox")
            .toAbsolutePath()
            .normalize();
    private final ExecutorService worker = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "Daily Dress client wardrobe sync");
        thread.setDaemon(true);
        return thread;
    });

    private boolean connected;
    private boolean preparing;
    private int ticks;
    private String lastMetadataFingerprint = "";
    private PreparedUpload pendingUpload;

    public void register() {
        ClientPlayConnectionEvents.JOIN.register((handler, sender, client) -> {
            connected = true;
            preparing = false;
            pendingUpload = null;
            lastMetadataFingerprint = "";
            ticks = 80;
        });
        ClientPlayConnectionEvents.DISCONNECT.register((handler, client) -> {
            connected = false;
            preparing = false;
            pendingUpload = null;
            lastMetadataFingerprint = "";
        });
        ClientTickEvents.END_CLIENT_TICK.register(this::onTick);
        ClientPlayNetworking.registerGlobalReceiver(
                SyncPackets.DecisionPayload.TYPE,
                (payload, context) -> context.client().execute(() -> handleDecision(context.client(), payload))
        );
        ClientPlayNetworking.registerGlobalReceiver(
                SyncPackets.ResultPayload.TYPE,
                (payload, context) -> context.client().execute(() -> handleResult(context.client(), payload))
        );
    }

    private void onTick(Minecraft client) {
        if (!connected || client.getConnection() == null) return;
        if (++ticks < 100) return;
        ticks = 0;
        if (preparing || pendingUpload != null || !ClientPlayNetworking.canSend(SyncPackets.OfferPayload.TYPE)) return;

        preparing = true;
        String previousMetadata = lastMetadataFingerprint;
        CompletableFuture
                .supplyAsync(() -> {
                    try {
                        return prepareIfChanged(previousMetadata);
                    } catch (Exception exception) {
                        throw new RuntimeException(exception);
                    }
                }, worker)
                .whenComplete((scan, error) -> client.execute(() -> {
                    preparing = false;
                    if (!connected || client.getConnection() == null) return;
                    if (error != null) {
                        DailyDress.LOGGER.error("Could not prepare the Daily Dress sync outbox", error);
                        showError(client, "Daily Dress could not prepare the local sync wardrobe.");
                        return;
                    }
                    lastMetadataFingerprint = scan.metadataFingerprint;
                    if (scan.upload == null) return;
                    if (!ClientPlayNetworking.canSend(SyncPackets.OfferPayload.TYPE)) return;
                    pendingUpload = scan.upload;
                    ClientPlayNetworking.send(new SyncPackets.OfferPayload(
                            scan.upload.archiveHash,
                            scan.upload.fileCount,
                            scan.upload.archive.length
                    ));
                }));
    }

    private void handleDecision(Minecraft client, SyncPackets.DecisionPayload payload) {
        PreparedUpload upload = pendingUpload;
        if (upload == null || !upload.archiveHash.equals(payload.hash())) return;

        if (payload.decision() == SyncPackets.DECISION_UPLOAD) {
            if (ClientPlayNetworking.canSend(SyncPackets.ArchivePayload.TYPE)) {
                ClientPlayNetworking.send(new SyncPackets.ArchivePayload(upload.archiveHash, upload.archive));
            } else {
                pendingUpload = null;
                showError(client, "Roses cannot receive the Daily Dress wardrobe archive.");
            }
            return;
        }

        pendingUpload = null;
        if (payload.decision() == SyncPackets.DECISION_UP_TO_DATE) {
            DailyDress.LOGGER.info("Daily Dress personal wardrobe is already synchronized.");
        } else {
            DailyDress.LOGGER.warn("Daily Dress wardrobe offer rejected: {}", payload.message());
            showError(client, payload.message());
        }
    }

    private void handleResult(Minecraft client, SyncPackets.ResultPayload payload) {
        PreparedUpload upload = pendingUpload;
        if (upload == null || !upload.archiveHash.equals(payload.hash())) return;
        pendingUpload = null;
        if (payload.success()) {
            DailyDress.LOGGER.info("Daily Dress personal wardrobe synchronized through Minecraft.");
        } else {
            DailyDress.LOGGER.warn("Daily Dress wardrobe sync failed: {}", payload.message());
            showError(client, payload.message());
        }
    }

    private DirectoryScan prepareIfChanged(String previousMetadata) throws IOException {
        if (!Files.isDirectory(outbox)) return new DirectoryScan("missing", null);
        List<Path> files;
        try (var paths = Files.walk(outbox)) {
            files = paths
                    .filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".png"))
                    .sorted(Comparator.comparing(path -> outbox.relativize(path).toString().toLowerCase(Locale.ROOT)))
                    .toList();
        }
        String metadata = metadataFingerprint(files);
        if (metadata.equals(previousMetadata) || files.isEmpty()) return new DirectoryScan(metadata, null);
        if (files.size() > SyncPackets.MAX_FILES) throw new IOException("The sync outbox contains more than " + SyncPackets.MAX_FILES + " skins");

        long uncompressed = 0;
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(bytes)) {
            for (Path path : files) {
                long fileBytes = Files.size(path);
                if (fileBytes > SyncPackets.MAX_FILE_BYTES) throw new IOException(path.getFileName() + " is too large");
                uncompressed += fileBytes;
                if (uncompressed > SyncPackets.MAX_UNCOMPRESSED_BYTES) throw new IOException("The sync outbox is too large");

                BufferedImage image = ImageIO.read(path.toFile());
                if (image == null || image.getWidth() != 64 || image.getHeight() != 64) {
                    throw new IOException(path.getFileName() + " is not a valid 64x64 PNG skin");
                }

                String relative = outbox.relativize(path).toString().replace('\\', '/');
                ZipEntry entry = new ZipEntry(relative);
                entry.setTime(0L);
                zip.putNextEntry(entry);
                Files.copy(path, zip);
                zip.closeEntry();
            }
        }
        byte[] archive = bytes.toByteArray();
        if (archive.length > SyncPackets.MAX_ARCHIVE_BYTES) throw new IOException("The compressed sync wardrobe is too large");
        return new DirectoryScan(metadata, new PreparedUpload(sha256(archive), archive, files.size()));
    }

    private String metadataFingerprint(List<Path> files) throws IOException {
        MessageDigest digest = digest();
        for (Path path : files) {
            String line = outbox.relativize(path).toString().replace('\\', '/')
                    + '\u0000' + Files.size(path)
                    + '\u0000' + Files.getLastModifiedTime(path).toMillis()
                    + '\n';
            digest.update(line.getBytes(StandardCharsets.UTF_8));
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static String sha256(byte[] bytes) throws IOException {
        return HexFormat.of().formatHex(digest().digest(bytes));
    }

    private static MessageDigest digest() throws IOException {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IOException("SHA-256 unavailable", exception);
        }
    }

    private static void showError(Minecraft client, String text) {
        if (client.player != null) {
            client.player.sendSystemMessage(Component.literal(text).withStyle(ChatFormatting.RED));
        }
    }

    private record DirectoryScan(String metadataFingerprint, PreparedUpload upload) {}
    private record PreparedUpload(String archiveHash, byte[] archive, int fileCount) {}
}
