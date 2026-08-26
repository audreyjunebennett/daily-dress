package dev.roses.dailydress.client;

import net.fabricmc.api.ClientModInitializer;

public final class DailyDressClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        new ClientWardrobeSync().register();
    }
}
