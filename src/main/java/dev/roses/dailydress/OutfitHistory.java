package dev.roses.dailydress;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * A bounded outfit timeline with a movable cursor. The fields are intentionally
 * serializable by Gson so the cursor survives server restarts.
 */
public final class OutfitHistory {
    static final int MAX_ENTRIES = 32;

    private List<String> entries = new ArrayList<>();
    private int cursor = -1;

    public synchronized Optional<String> current() {
        sanitize();
        return cursor >= 0 ? Optional.of(entries.get(cursor)) : Optional.empty();
    }

    public synchronized Optional<Selection> previousAvailable(Set<String> availableOutfits) {
        sanitize();
        return findAvailable(cursor - 1, -1, availableOutfits);
    }

    public synchronized Optional<Selection> nextAvailable(Set<String> availableOutfits) {
        sanitize();
        return findAvailable(cursor + 1, 1, availableOutfits);
    }

    public synchronized boolean activate(Selection selection) {
        sanitize();
        if (selection == null || selection.index() < 0 || selection.index() >= entries.size()) return false;
        if (!entries.get(selection.index()).equals(selection.outfitId())) return false;
        cursor = selection.index();
        return true;
    }

    public synchronized void record(String outfitId) {
        sanitize();
        if (outfitId == null || outfitId.isBlank()) return;
        if (cursor >= 0 && entries.get(cursor).equals(outfitId)) return;

        if (cursor + 1 < entries.size()) {
            entries.subList(cursor + 1, entries.size()).clear();
        }
        entries.add(outfitId);
        cursor = entries.size() - 1;
        trimToLimit();
    }

    synchronized List<String> snapshot() {
        sanitize();
        return List.copyOf(entries);
    }

    synchronized int cursor() {
        sanitize();
        return cursor;
    }

    synchronized void sanitize() {
        if (entries == null) entries = new ArrayList<>();
        entries.removeIf(entry -> entry == null || entry.isBlank());
        if (entries.isEmpty()) {
            cursor = -1;
            return;
        }
        cursor = Math.clamp(cursor, 0, entries.size() - 1);
        trimToLimit();
    }

    private Optional<Selection> findAvailable(int start, int step, Set<String> availableOutfits) {
        if (availableOutfits == null || availableOutfits.isEmpty()) return Optional.empty();
        for (int index = start; index >= 0 && index < entries.size(); index += step) {
            String outfitId = entries.get(index);
            if (availableOutfits.contains(outfitId)) return Optional.of(new Selection(outfitId, index));
        }
        return Optional.empty();
    }

    private void trimToLimit() {
        int overflow = entries.size() - MAX_ENTRIES;
        if (overflow <= 0) return;
        entries.subList(0, overflow).clear();
        cursor = Math.max(0, cursor - overflow);
    }

    public record Selection(String outfitId, int index) {}
}
