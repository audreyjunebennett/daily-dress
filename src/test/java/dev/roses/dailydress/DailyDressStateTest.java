package dev.roses.dailydress;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.slf4j.Logger;
import org.slf4j.helpers.NOPLogger;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class DailyDressStateTest {
    private static final String PLAYER = "00000000-0000-0000-0000-000000000001";
    private static final Logger LOGGER = NOPLogger.NOP_LOGGER;

    @TempDir
    Path temporaryDirectory;

    @Test
    void historyAndCursorSurviveSavingAndReloading() {
        Path statePath = temporaryDirectory.resolve("state.json");
        DailyDressState state = new DailyDressState();
        OutfitHistory history = state.outfitHistory(PLAYER);
        history.record("a.png");
        history.record("b.png");
        history.record("c.png");
        history.activate(history.previousAvailable(Set.of("a.png", "b.png", "c.png")).orElseThrow());

        state.save(statePath, LOGGER);
        DailyDressState reloaded = DailyDressState.load(statePath, LOGGER);

        OutfitHistory restored = reloaded.outfitHistory(PLAYER);
        assertEquals("b.png", restored.current().orElseThrow());
        assertEquals("c.png", restored.nextAvailable(Set.of("a.png", "b.png", "c.png"))
                .orElseThrow().outfitId());
    }

    @Test
    void legacyLastOutfitBecomesTheFirstHistoryEntry() throws Exception {
        Path statePath = temporaryDirectory.resolve("state.json");
        Files.writeString(statePath, """
                {
                  "lastOutfit": {
                    "%s": "legacy.png"
                  }
                }
                """.formatted(PLAYER));

        DailyDressState reloaded = DailyDressState.load(statePath, LOGGER);

        assertEquals("legacy.png", reloaded.outfitHistory(PLAYER).current().orElseThrow());
        assertTrue(reloaded.outfitHistory(PLAYER).previousAvailable(Set.of("legacy.png")).isEmpty());
    }
}
