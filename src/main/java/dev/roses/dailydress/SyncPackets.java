package dev.roses.dailydress;

import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.Identifier;

public final class SyncPackets {
    public static final int MAX_FILES = 512;
    public static final int MAX_FILE_BYTES = 256 * 1024;
    public static final int MAX_ARCHIVE_BYTES = 32 * 1024 * 1024;
    public static final long MAX_UNCOMPRESSED_BYTES = 64L * 1024L * 1024L;

    public static final int DECISION_UP_TO_DATE = 0;
    public static final int DECISION_UPLOAD = 1;
    public static final int DECISION_REJECTED = 2;

    private static boolean registered;

    private SyncPackets() {}

    public static synchronized void register() {
        if (registered) return;
        registered = true;
        PayloadTypeRegistry.serverboundPlay().register(OfferPayload.TYPE, OfferPayload.CODEC);
        PayloadTypeRegistry.serverboundPlay().registerLarge(
                ArchivePayload.TYPE,
                ArchivePayload.CODEC,
                MAX_ARCHIVE_BYTES + 1024
        );
        PayloadTypeRegistry.clientboundPlay().register(DecisionPayload.TYPE, DecisionPayload.CODEC);
        PayloadTypeRegistry.clientboundPlay().register(ResultPayload.TYPE, ResultPayload.CODEC);
    }

    private static Identifier id(String path) {
        return Identifier.fromNamespaceAndPath(DailyDress.MOD_ID, path);
    }

    public record OfferPayload(String hash, int fileCount, int archiveBytes) implements CustomPacketPayload {
        public static final Type<OfferPayload> TYPE = new Type<>(id("wardrobe_offer"));
        public static final StreamCodec<RegistryFriendlyByteBuf, OfferPayload> CODEC = StreamCodec.of(
                (buffer, payload) -> {
                    buffer.writeUtf(payload.hash, 64);
                    buffer.writeVarInt(payload.fileCount);
                    buffer.writeVarInt(payload.archiveBytes);
                },
                buffer -> new OfferPayload(buffer.readUtf(64), buffer.readVarInt(), buffer.readVarInt())
        );

        @Override
        public Type<OfferPayload> type() {
            return TYPE;
        }
    }

    public record ArchivePayload(String hash, byte[] archive) implements CustomPacketPayload {
        public static final Type<ArchivePayload> TYPE = new Type<>(id("wardrobe_archive"));
        public static final StreamCodec<RegistryFriendlyByteBuf, ArchivePayload> CODEC = StreamCodec.of(
                (buffer, payload) -> {
                    buffer.writeUtf(payload.hash, 64);
                    buffer.writeByteArray(payload.archive);
                },
                buffer -> new ArchivePayload(buffer.readUtf(64), buffer.readByteArray(MAX_ARCHIVE_BYTES))
        );

        @Override
        public Type<ArchivePayload> type() {
            return TYPE;
        }
    }

    public record DecisionPayload(String hash, int decision, String message) implements CustomPacketPayload {
        public static final Type<DecisionPayload> TYPE = new Type<>(id("wardrobe_decision"));
        public static final StreamCodec<RegistryFriendlyByteBuf, DecisionPayload> CODEC = StreamCodec.of(
                (buffer, payload) -> {
                    buffer.writeUtf(payload.hash, 64);
                    buffer.writeVarInt(payload.decision);
                    buffer.writeUtf(payload.message, 256);
                },
                buffer -> new DecisionPayload(buffer.readUtf(64), buffer.readVarInt(), buffer.readUtf(256))
        );

        @Override
        public Type<DecisionPayload> type() {
            return TYPE;
        }
    }

    public record ResultPayload(String hash, boolean success, String message) implements CustomPacketPayload {
        public static final Type<ResultPayload> TYPE = new Type<>(id("wardrobe_result"));
        public static final StreamCodec<RegistryFriendlyByteBuf, ResultPayload> CODEC = StreamCodec.of(
                (buffer, payload) -> {
                    buffer.writeUtf(payload.hash, 64);
                    buffer.writeBoolean(payload.success);
                    buffer.writeUtf(payload.message, 256);
                },
                buffer -> new ResultPayload(buffer.readUtf(64), buffer.readBoolean(), buffer.readUtf(256))
        );

        @Override
        public Type<ResultPayload> type() {
            return TYPE;
        }
    }
}
