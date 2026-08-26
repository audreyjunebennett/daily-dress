package dev.roses.dailydress;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import org.slf4j.Logger;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

public final class DailyDressConfig {
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    public boolean enabledByDefault = false;
    public boolean useSlimModel = true;
    public String skinModel = "auto";
    public boolean includeSharedWardrobe = false;
    public boolean announceOutfit = false;
    public boolean avoidImmediateRepeats = true;
    public String sharedWardrobe = "wardrobe/shared";
    public String personalWardrobes = "wardrobe/players";
    public Set<String> enabledPlayers = new HashSet<>();

    public static DailyDressConfig load(Path path, Logger logger) {
        try {
            Files.createDirectories(path.getParent());
            if (Files.exists(path)) {
                try (Reader reader = Files.newBufferedReader(path)) {
                    DailyDressConfig loaded = GSON.fromJson(reader, DailyDressConfig.class);
                    if (loaded != null) {
                        loaded.sanitize();
                        return loaded;
                    }
                }
            }
        } catch (Exception exception) {
            logger.error("Could not read Daily Dress config at {}", path, exception);
        }

        DailyDressConfig config = new DailyDressConfig();
        config.save(path, logger);
        return config;
    }

    public synchronized void save(Path path, Logger logger) {
        sanitize();
        Path temporary = path.resolveSibling(path.getFileName() + ".tmp");
        try {
            Files.createDirectories(path.getParent());
            try (Writer writer = Files.newBufferedWriter(temporary)) {
                GSON.toJson(this, writer);
            }
            try {
                Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            } catch (IOException unsupportedAtomicMove) {
                Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException exception) {
            logger.error("Could not save Daily Dress config at {}", path, exception);
        }
    }

    public synchronized boolean isEnabled(UUID playerId) {
        return enabledPlayers.contains(playerId.toString().toLowerCase(Locale.ROOT)) || enabledByDefault;
    }

    public synchronized void setEnabled(UUID playerId, boolean enabled) {
        String id = playerId.toString().toLowerCase(Locale.ROOT);
        if (enabled) {
            enabledPlayers.add(id);
        } else {
            enabledPlayers.remove(id);
        }
    }

    private void sanitize() {
        if (enabledPlayers == null) enabledPlayers = new HashSet<>();
        if (sharedWardrobe == null || sharedWardrobe.isBlank()) sharedWardrobe = "wardrobe/shared";
        if (personalWardrobes == null || personalWardrobes.isBlank()) personalWardrobes = "wardrobe/players";
        if (skinModel == null || (!skinModel.equalsIgnoreCase("auto")
                && !skinModel.equalsIgnoreCase("slim")
                && !skinModel.equalsIgnoreCase("classic"))) skinModel = "auto";
    }
}
