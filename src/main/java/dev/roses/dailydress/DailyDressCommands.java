package dev.roses.dailydress;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.ChatFormatting;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;

import java.util.Optional;

public final class DailyDressCommands {
    private final DailyDress owner;
    private final WardrobeService wardrobe;

    public DailyDressCommands(DailyDress owner, WardrobeService wardrobe) {
        this.owner = owner;
        this.wardrobe = wardrobe;
    }

    public void register() {
        CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) -> register(dispatcher));
    }

    private void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("dailydress")
                .executes(context -> status(context.getSource()))
                .then(Commands.literal("on").executes(context -> setEnabled(context.getSource(), true)))
                .then(Commands.literal("off").executes(context -> setEnabled(context.getSource(), false)))
                .then(Commands.literal("next").executes(context -> next(context.getSource())))
                .then(Commands.literal("batch")
                        .executes(context -> batchStatus(context.getSource()))
                        .then(Commands.argument("filter", StringArgumentType.word())
                                .executes(context -> setBatch(
                                        context.getSource(),
                                        StringArgumentType.getString(context, "filter")
                                )))
                )
                .then(Commands.literal("flag")
                        .executes(context -> flag(context.getSource(), ""))
                        .then(Commands.argument("note", StringArgumentType.greedyString())
                                .executes(context -> flag(
                                        context.getSource(),
                                        StringArgumentType.getString(context, "note")
                                )))
                )
                .then(Commands.literal("flags").executes(context -> flags(context.getSource())))
                .then(Commands.literal("status").executes(context -> status(context.getSource())))
                .then(Commands.literal("reload").executes(context -> reload(context.getSource())))
        );
    }

    private int setEnabled(CommandSourceStack source, boolean enabled) throws CommandSyntaxException {
        ServerPlayer player = source.getPlayerOrException();
        owner.config().setEnabled(player.getUUID(), enabled);
        owner.saveConfig();
        player.sendSystemMessage(message(enabled
                ? "Daily Dress is on. Sleep through the night to wake up in a new outfit ✿"
                : "Daily Dress is off for you.", enabled ? ChatFormatting.LIGHT_PURPLE : ChatFormatting.GRAY));
        return 1;
    }

    private int next(CommandSourceStack source) throws CommandSyntaxException {
        ServerPlayer player = source.getPlayerOrException();
        wardrobe.dressNow(player, false);
        return 1;
    }

    private int flag(CommandSourceStack source, String note) throws CommandSyntaxException {
        ServerPlayer player = source.getPlayerOrException();
        Optional<String> flagged = wardrobe.flagCurrentAndDressNext(player, note);
        if (flagged.isEmpty()) {
            player.sendSystemMessage(message(
                    "Daily Dress could not identify the current wardrobe file, so nothing was flagged.",
                    ChatFormatting.RED
            ));
            return 0;
        }
        String noteSuffix = note == null || note.isBlank() ? "" : " Note saved: “" + note.strip() + "”.";
        player.sendSystemMessage(message(
                "Flagged “" + flagged.get() + "”; this exact version will not return. Choosing another outfit now." + noteSuffix,
                ChatFormatting.LIGHT_PURPLE
        ));
        return 1;
    }

    private int batchStatus(CommandSourceStack source) throws CommandSyntaxException {
        ServerPlayer player = source.getPlayerOrException();
        String batch = wardrobe.activeBatch(player);
        int eligible = wardrobe.countSkins(player);
        player.sendSystemMessage(message(
                "Daily Dress sleep batch: “" + batch + "” (" + eligible + " outfit" + (eligible == 1 ? "" : "s")
                        + "). Use /dailydress batch all, favorites, casual, seasonal, dresses, or favorites+casual.",
                ChatFormatting.LIGHT_PURPLE
        ));
        return eligible;
    }

    private int setBatch(CommandSourceStack source, String requested) throws CommandSyntaxException {
        ServerPlayer player = source.getPlayerOrException();
        int count = wardrobe.setBatch(player, requested);
        if (count == 0) {
            player.sendSystemMessage(message(
                    "No synced outfits match “" + requested + "”, so your current sleep batch was not changed.",
                    ChatFormatting.RED
            ));
            return 0;
        }
        player.sendSystemMessage(message(
                "Daily Dress will now choose from “" + wardrobe.activeBatch(player) + "” after sleep (" + count
                        + " outfit" + (count == 1 ? "" : "s") + ").",
                ChatFormatting.LIGHT_PURPLE
        ));
        return count;
    }

    private int flags(CommandSourceStack source) throws CommandSyntaxException {
        ServerPlayer player = source.getPlayerOrException();
        int count = wardrobe.flaggedCount(player);
        player.sendSystemMessage(message(
                "You have " + count + " flagged Daily Dress outfit" + (count == 1 ? "" : "s")
                        + ". Corrected files with changed pixels become eligible automatically.",
                ChatFormatting.LIGHT_PURPLE
        ));
        return count;
    }

    private int status(CommandSourceStack source) throws CommandSyntaxException {
        ServerPlayer player = source.getPlayerOrException();
        boolean enabled = owner.config().isEnabled(player.getUUID());
        int count = wardrobe.countSkins(player);
        int total = wardrobe.countAllSkins(player);
        player.sendSystemMessage(message(
                "Daily Dress is " + (enabled ? "ON" : "OFF") + " for you; " + count
                        + " eligible of " + total + " valid outfits in batch “" + wardrobe.activeBatch(player) + "”; "
                        + wardrobe.flaggedCount(player) + " flagged; model: " + owner.config().skinModel + ".",
                enabled ? ChatFormatting.LIGHT_PURPLE : ChatFormatting.GRAY
        ));
        return count;
    }

    private int reload(CommandSourceStack source) throws CommandSyntaxException {
        ServerPlayer player = source.getPlayerOrException();
        owner.reloadConfig();
        wardrobe.ensureFolders();
        player.sendSystemMessage(message("Daily Dress reloaded; found " + wardrobe.countSkins(player) + " outfits.", ChatFormatting.LIGHT_PURPLE));
        return 1;
    }

    private static Component message(String text, ChatFormatting color) {
        return Component.literal(text).withStyle(color);
    }
}
