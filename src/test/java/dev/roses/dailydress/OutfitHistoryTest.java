package dev.roses.dailydress;

import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class OutfitHistoryTest {
    @Test
    void previousThenNextMovesBackAndForwardThroughExistingHistory() {
        OutfitHistory history = historyWith("a.png", "b.png", "c.png");

        OutfitHistory.Selection previous = history.previousAvailable(Set.of("a.png", "b.png", "c.png"))
                .orElseThrow();
        assertEquals("b.png", previous.outfitId());
        assertTrue(history.activate(previous));

        OutfitHistory.Selection next = history.nextAvailable(Set.of("a.png", "b.png", "c.png"))
                .orElseThrow();
        assertEquals("c.png", next.outfitId());
        assertTrue(history.activate(next));
        assertEquals("c.png", history.current().orElseThrow());
    }

    @Test
    void recordingAfterGoingBackReplacesTheForwardBranch() {
        OutfitHistory history = historyWith("a.png", "b.png", "c.png");
        history.activate(history.previousAvailable(Set.of("a.png", "b.png", "c.png")).orElseThrow());

        history.record("d.png");

        assertEquals(java.util.List.of("a.png", "b.png", "d.png"), history.snapshot());
        assertTrue(history.nextAvailable(Set.of("a.png", "b.png", "c.png", "d.png")).isEmpty());
    }

    @Test
    void navigationSkipsOutfitsThatAreNoLongerAvailable() {
        OutfitHistory history = historyWith("a.png", "removed-b.png", "removed-c.png", "d.png");

        OutfitHistory.Selection previous = history.previousAvailable(Set.of("a.png", "d.png"))
                .orElseThrow();
        assertEquals("a.png", previous.outfitId());
        assertTrue(history.activate(previous));

        OutfitHistory.Selection next = history.nextAvailable(Set.of("a.png", "d.png"))
                .orElseThrow();
        assertEquals("d.png", next.outfitId());
    }

    @Test
    void duplicateCurrentOutfitIsNotRecordedTwiceAndHistoryStaysBounded() {
        OutfitHistory history = new OutfitHistory();
        for (int index = 0; index < OutfitHistory.MAX_ENTRIES + 5; index++) {
            history.record("outfit-" + index);
        }
        history.record("outfit-" + (OutfitHistory.MAX_ENTRIES + 4));

        assertEquals(OutfitHistory.MAX_ENTRIES, history.snapshot().size());
        assertEquals("outfit-5", history.snapshot().getFirst());
        assertEquals("outfit-36", history.current().orElseThrow());
    }

    private static OutfitHistory historyWith(String... outfits) {
        OutfitHistory history = new OutfitHistory();
        for (String outfit : outfits) history.record(outfit);
        return history;
    }
}
