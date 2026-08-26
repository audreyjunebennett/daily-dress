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
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

public final class DailyDressState {
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    public Map<String, CachedSkin> skinCache = new HashMap<>();
    public Map<String, String> lastOutfit = new HashMap<>();
    public Map<String, Map<String, FlaggedOutfit>> flaggedOutfits = new HashMap<>();

    public record CachedSkin(String value, String signature) {}
    public record FlaggedOutfit(
            String outfitId,
            String contentSha256,
            String fileName,
            String playerName,
            String flaggedAt,
            String note
    ) {}

    public static DailyDressState load(Path path, Logger logger) {
        try {
            Files.createDirectories(path.getParent());
            if (Files.exists(path)) {
                try (Reader reader = Files.newBufferedReader(path)) {
                    DailyDressState loaded = GSON.fromJson(reader, DailyDressState.class);
                    if (loaded != null) {
                        loaded.sanitize();
                        return loaded;
                    }
                }
            }
        } catch (Exception exception) {
            logger.error("Could not read Daily Dress state at {}", path, exception);
        }
        return new DailyDressState();
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
            logger.error("Could not save Daily Dress state at {}", path, exception);
        }
    }

    public synchronized void saveFlagReport(Path path, Logger logger) {
        sanitize();
        Path temporary = path.resolveSibling(path.getFileName() + ".tmp");
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("description", "Daily Dress outfits flagged in-game. A changed contentSha256 means a corrected file may be selected again.");
        report.put("players", flaggedOutfits);
        try {
            Files.createDirectories(path.getParent());
            try (Writer writer = Files.newBufferedWriter(temporary)) {
                GSON.toJson(report, writer);
            }
            try {
                Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            } catch (IOException unsupportedAtomicMove) {
                Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException exception) {
            logger.error("Could not save Daily Dress flag report at {}", path, exception);
        }
    }

    private void sanitize() {
        if (skinCache == null) skinCache = new HashMap<>();
        if (lastOutfit == null) lastOutfit = new HashMap<>();
        if (flaggedOutfits == null) flaggedOutfits = new HashMap<>();
    }
}
