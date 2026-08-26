package dev.roses.dailydress;

import com.mojang.authlib.properties.Property;
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
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadLocalRandom;
import java.util.stream.Stream;

public final class WardrobeService implements AutoCloseable {
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
            player.sendSystemMessage(styled("Daily Dress could not find any valid 64×64 PNGs in your wardrobe.", ChatFormatting.RED));
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
        List<Path> skins = new ArrayList<>();
        if (owner.config().includeSharedWardrobe) {
            collectValidSkins(sharedWardrobe(), skins);
        }
        Path personal = personalWardrobe(player);
        try {
            Files.createDirectories(personal);
        } catch (IOException exception) {
            DailyDress.LOGGER.warn("Could not create personal wardrobe {}", personal, exception);
        }
        collectValidSkins(personal, skins);
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

    private void collectValidSkins(Path directory, List<Path> destination) {
        if (!Files.isDirectory(directory)) return;
        try (Stream<Path> files = Files.walk(directory)) {
            files.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".png"))
                    .filter(this::isValidSkin)
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

    private void apply(ServerPlayer player, Path chosen, boolean afterSleep) {
        final String cacheKey;
        try {
            cacheKey = (owner.config().useSlimModel ? "slim:" : "classic:") + sha256(chosen);
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
                        () -> SkinFetcher.setSkinFromFile(chosen.toAbsolutePath().toString(), owner.config().useSlimModel),
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

    @Override
    public void close() {
        uploader.shutdown();
        state.save(statePath, DailyDress.LOGGER);
    }
}
