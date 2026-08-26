package dev.roses.dailydress;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.loader.api.FabricLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Path;

public final class DailyDress implements ModInitializer {
    public static final String MOD_ID = "daily_dress";
    public static final Logger LOGGER = LoggerFactory.getLogger("Daily Dress");

    private final Path root = FabricLoader.getInstance().getConfigDir().resolve("daily-dress").toAbsolutePath().normalize();
    private final Path configPath = root.resolve("config.json");
    private DailyDressConfig config;
    private WardrobeService wardrobe;
    private ServerWardrobeSync wardrobeSync;

    @Override
    public void onInitialize() {
        SyncPackets.register();
        reloadConfig();
        wardrobe = new WardrobeService(this, root);
        wardrobeSync = new ServerWardrobeSync(this, wardrobe);
        wardrobeSync.register();
        new SleepWatcher(wardrobe).register();
        new DailyDressCommands(this, wardrobe).register();
        ServerLifecycleEvents.SERVER_STOPPING.register(server -> {
            wardrobeSync.close();
            wardrobe.close();
        });
        LOGGER.info("Daily Dress is ready. Personal wardrobes: {}", wardrobe.personalWardrobes());
    }

    public DailyDressConfig config() {
        return config;
    }

    public void reloadConfig() {
        config = DailyDressConfig.load(configPath, LOGGER);
    }

    public void saveConfig() {
        config.save(configPath, LOGGER);
    }
}
