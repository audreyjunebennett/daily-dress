package dev.roses.dailydress;

import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.Level;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class SleepWatcher {
    private final WardrobeService wardrobe;
    private final Map<ResourceKey<Level>, Snapshot> snapshots = new HashMap<>();

    public SleepWatcher(WardrobeService wardrobe) {
        this.wardrobe = wardrobe;
    }

    public void register() {
        ServerTickEvents.START_LEVEL_TICK.register(this::startWorldTick);
        ServerTickEvents.END_LEVEL_TICK.register(this::endWorldTick);
    }

    private void startWorldTick(ServerLevel level) {
        if (!Level.OVERWORLD.equals(level.dimension())) return;
        List<UUID> sleepers = level.players().stream()
                .filter(ServerPlayer::isSleeping)
                .map(ServerPlayer::getUUID)
                .toList();
        snapshots.put(level.dimension(), new Snapshot(level.getOverworldClockTime(), sleepers));
    }

    private void endWorldTick(ServerLevel level) {
        if (!Level.OVERWORLD.equals(level.dimension())) return;
        Snapshot before = snapshots.remove(level.dimension());
        if (before == null || before.sleepers().isEmpty()) return;

        long after = level.getOverworldClockTime();
        long change = after - before.dayTime();
        boolean crossedIntoMorning = change > 100
                && Math.floorDiv(after, 24_000L) > Math.floorDiv(before.dayTime(), 24_000L)
                && Math.floorMod(after, 24_000L) < 2_000L;

        if (!crossedIntoMorning) return;
        for (UUID sleeperId : before.sleepers()) {
            ServerPlayer sleeper = level.getServer().getPlayerList().getPlayer(sleeperId);
            if (sleeper != null) wardrobe.dressAfterSleep(sleeper);
        }
    }

    private record Snapshot(long dayTime, List<UUID> sleepers) {}
}
