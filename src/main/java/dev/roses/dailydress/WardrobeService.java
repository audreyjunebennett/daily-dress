package dev.roses.dailydress;

import com.mojang.authlib.properties.Property;
import com.google.gson.Gson;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import org.samo_lego.fabrictailor.casts.TailoredPlayer;
import org.samo_lego.fabrictailor.util.SkinFetcher;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HexFormat;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadLocalRandom;
import java.util.stream.Stream;

public final class WardrobeService implements AutoCloseable {
    private static final Gson GSON = new Gson();
    private static final String METADATA_FILE = "daily-dress-wardrobe.json";
    private final DailyDress owner;
    private final Path root;
    private final Path statePath;
    private final Path flagReportPath;
    private final DailyDressState state;
    private final ExecutorService uploader = Executors.newFixedThreadPool(2, runnable -> {
        Thread thread = new Thread(runnable, "Daily Dress skin uploader");
        thread.setDaemon(true);
        return thread;
    });
    private final ConcurrentHashMap<String, CompletableFuture<Optional<Property>>> pendingUploads = new ConcurrentHashMap<>();

    public WardrobeService(DailyDress owner, Path root) {
        this.owner = owner;
        this.root = root;
        this.statePath = root.resolve("state.json");
        this.flagReportPath = root.resolve("FLAGGED OUTFITS.json");
        this.state = DailyDressState.load(statePath, DailyDress.LOGGER);
        ensureFolders();
    }

    public void ensureFolders() {
        try {
            Files.createDirectories(sharedWardrobe());
            Files.createDirectories(personalWardrobes());
        } catch (IOException exception) {
            DailyDress.LOGGER.error("Could not create Daily Dress wardrobe folders", exception);
        }
    }

    public void dressAfterSleep(ServerPlayer player) {
        if (owner.config().isEnabled(player.getUUID())) {
            dressNow(player, true);
        }
    }

    public void dressNow(ServerPlayer player, boolean afterSleep) {
        List<Path> choices = findSkins(player);
        if (choices.isEmpty()) {
            String batch = activeBatch(player);
            String detail = batch.equals("all")
                    ? "any valid 64×64 PNGs in your wardrobe"
                    : "any outfits in your active “" + batch + "” batch; use /dailydress batch all to reset it";
            player.sendSystemMessage(styled("Daily Dress could not find " + detail + ".", ChatFormatting.RED));
            return;
        }

        choices.removeIf(path -> isFlaggedVersion(player, path));
        if (choices.isEmpty()) {
            player.sendSystemMessage(styled(
                    "Daily Dress found outfits, but every current version is flagged. Regenerate one or clear its flag from the report.",
                    ChatFormatting.RED
            ));
            return;
        }

        String playerKey = player.getUUID().toString();
        String previous = state.lastOutfit.get(playerKey);
        if (owner.config().avoidImmediateRepeats && choices.size() > 1 && previous != null) {
            choices.removeIf(path -> outfitId(path).equals(previous));
        }

        Path chosen = choices.get(ThreadLocalRandom.current().nextInt(choices.size()));
        apply(player, chosen, afterSleep);
    }

    public Optional<String> flagCurrentAndDressNext(ServerPlayer player, String note) {
        String playerKey = player.getUUID().toString();
        String currentId = state.lastOutfit.get(playerKey);
        if (currentId == null || currentId.isBlank()) return Optional.empty();

        Optional<Path> currentPath = findSkins(player).stream()
                .filter(path -> outfitId(path).equals(currentId))
                .findFirst();
        if (currentPath.isEmpty()) return Optional.empty();

        Path path = currentPath.get();
        final String contentHash;
        try {
            contentHash = sha256(path);
        } catch (IOException exception) {
            DailyDress.LOGGER.error("Could not hash flagged outfit {}", path, exception);
            return Optional.empty();
        }

        String cleanedNote = note == null ? "" : note.strip();
        if (cleanedNote.length() > 240) cleanedNote = cleanedNote.substring(0, 240);
        DailyDressState.FlaggedOutfit flagged = new DailyDressState.FlaggedOutfit(
                currentId,
                contentHash,
                path.getFileName().toString(),
                player.getGameProfile().name(),
                Instant.now().toString(),
                cleanedNote
        );
        synchronized (state) {
            state.flaggedOutfits.computeIfAbsent(playerKey, ignored -> new java.util.LinkedHashMap<>())
                    .put(currentId, flagged);
        }
        state.save(statePath, DailyDress.LOGGER);
        state.saveFlagReport(flagReportPath, DailyDress.LOGGER);
        String name = displayName(path);
        DailyDress.LOGGER.info("{} flagged Daily Dress outfit {} ({})", player.getGameProfile().name(), currentId, cleanedNote);
        dressNow(player, false);
        return Optional.of(name);
    }

    public int flaggedCount(ServerPlayer player) {
        Map<String, DailyDressState.FlaggedOutfit> flags = state.flaggedOutfits.get(player.getUUID().toString());
        return flags == null ? 0 : flags.size();
    }

    public Path flagReportPath() {
        return flagReportPath;
    }

    public int countSkins(ServerPlayer player) {
        return findSkins(player).size();
    }

    public int countAllSkins(ServerPlayer player) {
        return findSkins(player, "all").size();
    }

    public String activeBatch(ServerPlayer player) {
        return state.activeBatches.getOrDefault(player.getUUID().toString(), "all");
    }

    public int setBatch(ServerPlayer player, String requested) {
        String batch = normalizeBatch(requested);
        int count = findSkins(player, batch).size();
        if (count == 0 && !batch.equals("all")) return 0;
        state.activeBatches.put(player.getUUID().toString(), batch);
        state.save(statePath, DailyDress.LOGGER);
        return count;
    }

    public Path sharedWardrobe() {
        return resolveInsideRoot(owner.config().sharedWardrobe);
    }

    public Path personalWardrobes() {
        return resolveInsideRoot(owner.config().personalWardrobes);
    }

    public Path personalWardrobe(ServerPlayer player) {
        return personalWardrobe(player.getUUID());
    }

    public Path personalWardrobe(java.util.UUID playerId) {
        return personalWardrobes().resolve(playerId.toString());
    }

    public Path root() {
        return root;
    }

    private List<Path> findSkins(ServerPlayer player) {
        return findSkins(player, activeBatch(player));
    }

    private List<Path> findSkins(ServerPlayer player, String batch) {
        List<Path> skins = new ArrayList<>();
        if (owner.config().includeSharedWardrobe) {
            collectValidSkins(sharedWardrobe(), skins, batch);
        }
        Path personal = personalWardrobe(player);
        try {
            Files.createDirectories(personal);
        } catch (IOException exception) {
            DailyDress.LOGGER.warn("Could not create personal wardrobe {}", personal, exception);
        }
        collectValidSkins(personal, skins, batch);
        return skins;
    }

    private boolean isFlaggedVersion(ServerPlayer player, Path path) {
        Map<String, DailyDressState.FlaggedOutfit> flags = state.flaggedOutfits.get(player.getUUID().toString());
        if (flags == null) return false;
        DailyDressState.FlaggedOutfit flagged = flags.get(outfitId(path));
        if (flagged == null || flagged.contentSha256() == null) return false;
        try {
            return flagged.contentSha256().equals(sha256(path));
        } catch (IOException exception) {
            DailyDress.LOGGER.warn("Could not compare flagged outfit version {}", path, exception);
            return true;
        }
    }

    private void collectValidSkins(Path directory, List<Path> destination, String batch) {
        if (!Files.isDirectory(directory)) return;
        WardrobeMetadata metadata = loadMetadata(directory);
        try (Stream<Path> files = Files.walk(directory)) {
            files.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".png"))
                    .filter(this::isValidSkin)
                    .filter(path -> matchesBatch(metadata, directory.relativize(path).toString().replace('\\', '/'), batch))
                    .forEach(destination::add);
        } catch (IOException exception) {
            DailyDress.LOGGER.warn("Could not scan wardrobe {}", directory, exception);
        }
    }

    private boolean isValidSkin(Path path) {
        try {
            BufferedImage image = ImageIO.read(path.toFile());
            return image != null && image.getWidth() == 64 && image.getHeight() == 64;
        } catch (IOException exception) {
            return false;
        }
    }

    private static String normalizeBatch(String requested) {
        if (requested == null || requested.isBlank()) return "all";
        String normalized = requested.strip().toLowerCase(Locale.ROOT)
                .replace(',', '+')
                .replace('&', '+')
                .replace(" ", "");
        normalized = Arrays.stream(normalized.split("\\+"))
                .map(part -> part.equals("favorite") ? "favorites" : part)
                .reduce((left, right) -> left + "+" + right)
                .orElse("all");
        if (normalized.equals("kept")) return "all";
        if (!normalized.matches("[a-z0-9_-]+(?:\\+[a-z0-9_-]+)*")) return "all";
        return normalized;
    }

    private static boolean matchesBatch(WardrobeMetadata metadata, String relative, String batch) {
        SkinMetadata skin = metadata.skins == null ? null : metadata.skins.get(relative);
        if (skin != null && "remove".equalsIgnoreCase(skin.status)) return false;
        String normalized = normalizeBatch(batch);
        if (normalized.equals("all")) return true;
        if (skin == null) return false;
        Set<String> requested = new HashSet<>(Arrays.asList(normalized.split("\\+")));
        if (requested.remove("favorites") && !skin.favorite) return false;
        if (requested.isEmpty()) return true;
        Set<String> tags = new HashSet<>();
        if (skin.tags != null) {
            skin.tags.stream().filter(java.util.Objects::nonNull)
                    .map(value -> value.toLowerCase(Locale.ROOT)).forEach(tags::add);
        }
        return requested.stream().allMatch(tags::contains);
    }

    private WardrobeMetadata loadMetadata(Path directory) {
        Path path = directory.resolve(METADATA_FILE);
        if (!Files.isRegularFile(path)) return new WardrobeMetadata();
        try (var reader = Files.newBufferedReader(path)) {
            WardrobeMetadata metadata = GSON.fromJson(reader, WardrobeMetadata.class);
            return metadata == null ? new WardrobeMetadata() : metadata;
        } catch (Exception exception) {
            DailyDress.LOGGER.warn("Could not read wardrobe metadata {}", path, exception);
            return new WardrobeMetadata();
        }
    }

    private SkinMetadata metadataFor(Path skinPath) {
        Path current = skinPath.getParent();
        Path normalizedRoot = root.toAbsolutePath().normalize();
        while (current != null && current.toAbsolutePath().normalize().startsWith(normalizedRoot)) {
            Path manifest = current.resolve(METADATA_FILE);
            if (Files.isRegularFile(manifest)) {
                WardrobeMetadata metadata = loadMetadata(current);
                String relative = current.relativize(skinPath).toString().replace('\\', '/');
                return metadata.skins == null ? null : metadata.skins.get(relative);
            }
            current = current.getParent();
        }
        return null;
    }

    private boolean isSlimModel(Path path) {
        String configured = owner.config().skinModel.toLowerCase(Locale.ROOT);
        if (configured.equals("slim")) return true;
        if (configured.equals("classic")) return false;
        SkinMetadata metadata = metadataFor(path);
        if (metadata != null && metadata.model != null) {
            if (metadata.model.equalsIgnoreCase("slim")) return true;
            if (metadata.model.equalsIgnoreCase("classic")) return false;
        }
        try {
            BufferedImage image = ImageIO.read(path.toFile());
            if (image == null) return owner.config().useSlimModel;
            int transparent = 0;
            int total = 0;
            int[][] strips = {{54, 20, 55, 31}, {46, 52, 47, 63}, {50, 16, 51, 19}, {42, 48, 43, 51}};
            for (int[] strip : strips) {
                for (int y = strip[1]; y <= strip[3]; y++) {
                    for (int x = strip[0]; x <= strip[2]; x++) {
                        total++;
                        transparent += ((image.getRGB(x, y) >>> 24) & 0xff) < 48 ? 1 : 0;
                    }
                }
            }
            return transparent >= Math.max(4, Math.round(total * 0.55f));
        } catch (IOException exception) {
            return owner.config().useSlimModel;
        }
    }

    private void apply(ServerPlayer player, Path chosen, boolean afterSleep) {
        final String cacheKey;
        final boolean slimModel = isSlimModel(chosen);
        try {
            cacheKey = (slimModel ? "slim:" : "classic:") + sha256(chosen);
        } catch (IOException exception) {
            player.sendSystemMessage(styled("Daily Dress could not read " + chosen.getFileName() + ".", ChatFormatting.RED));
            return;
        }

        DailyDressState.CachedSkin cached = state.skinCache.get(cacheKey);
        if (cached != null) {
            setSkin(player, chosen, new Property(TailoredPlayer.PROPERTY_TEXTURES, cached.value(), cached.signature()), afterSleep);
            return;
        }

        if (owner.config().announceOutfit) {
            player.sendSystemMessage(styled("Daily Dress is preparing “" + displayName(chosen) + "”…", ChatFormatting.LIGHT_PURPLE));
        }
        CompletableFuture<Optional<Property>> future = pendingUploads.computeIfAbsent(cacheKey, ignored ->
                CompletableFuture.supplyAsync(
                        () -> SkinFetcher.setSkinFromFile(chosen.toAbsolutePath().toString(), slimModel),
                        uploader
                )
        );

        MinecraftServer server = player.level().getServer();
        future.whenComplete((skin, error) -> {
            pendingUploads.remove(cacheKey, future);
            server.execute(() -> {
                ServerPlayer current = server.getPlayerList().getPlayer(player.getUUID());
                if (current == null) return;
                if (error != null || skin == null || skin.isEmpty()) {
                    DailyDress.LOGGER.error("Could not upload skin {}", chosen, error);
                    current.sendSystemMessage(styled("Daily Dress could not prepare that outfit. MineSkin may be busy; try /dailydress next in a moment.", ChatFormatting.RED));
                    return;
                }

                Property property = skin.get();
                state.skinCache.put(cacheKey, new DailyDressState.CachedSkin(property.value(), property.signature()));
                setSkin(current, chosen, property, afterSleep);
            });
        });
    }

    private void setSkin(ServerPlayer player, Path chosen, Property property, boolean afterSleep) {
        try {
            ((TailoredPlayer) player).fabrictailor_setSkin(property, true);
            state.lastOutfit.put(player.getUUID().toString(), outfitId(chosen));
            state.save(statePath, DailyDress.LOGGER);
            if (owner.config().announceOutfit) {
                String lead = afterSleep ? "Good morning! Today’s outfit is " : "Changed into ";
                player.sendSystemMessage(styled(lead + "“" + displayName(chosen) + "” ✿", ChatFormatting.LIGHT_PURPLE));
            }
        } catch (RuntimeException exception) {
            DailyDress.LOGGER.error("Could not apply skin {} to {}", chosen, player.getGameProfile().name(), exception);
            player.sendSystemMessage(styled("Daily Dress prepared the outfit but could not put it on.", ChatFormatting.RED));
        }
    }

    private Path resolveInsideRoot(String configured) {
        Path resolved = root.resolve(configured).normalize();
        return resolved.startsWith(root) ? resolved : root.resolve("wardrobe/shared");
    }

    private String outfitId(Path path) {
        try {
            return root.relativize(path.toAbsolutePath().normalize()).toString().replace('\\', '/');
        } catch (IllegalArgumentException exception) {
            return path.toAbsolutePath().normalize().toString();
        }
    }

    private static String displayName(Path path) {
        String name = path.getFileName().toString();
        int dot = name.lastIndexOf('.');
        if (dot > 0) name = name.substring(0, dot);
        return name.replace('_', ' ').replace('-', ' ');
    }

    private static String sha256(Path path) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(path)) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) >= 0) {
                    digest.update(buffer, 0, read);
                }
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static Component styled(String text, ChatFormatting color) {
        return Component.literal(text).withStyle(color);
    }

    private static final class WardrobeMetadata {
        Map<String, SkinMetadata> skins = Collections.emptyMap();
    }

    private static final class SkinMetadata {
        boolean favorite;
        String status = "unsorted";
        List<String> tags = Collections.emptyList();
        String model = "auto";
    }

    @Override
    public void close() {
        uploader.shutdown();
        state.save(statePath, DailyDress.LOGGER);
    }
}
