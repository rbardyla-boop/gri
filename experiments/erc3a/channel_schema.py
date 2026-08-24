from __future__ import annotations

from collections import OrderedDict

SAMPLE_RATE_HZ = 6400
SAMPLE_COUNT = 6400
TIME_COLUMN = "time_s"

LINE_ENDPOINTS: OrderedDict[str, tuple[str, str]] = OrderedDict(
    (
        ("Line_1_2_a", ("Bus_1_Line_01_02A", "Bus_2_Line_01_02A")),
        ("Line_1_2_b", ("Bus_1_Line_01_02B", "Bus_2_Line_01_02B")),
        ("Line_2_3_a", ("Bus_2_Line_02_03A", "Bus_3_Line_02_03A")),
        ("Line_2_3_b", ("Bus_2_Line_02_03B", "Bus_3_Line_02_03B")),
    )
)

PHASES = ("L1", "L2", "L3")


def _channel_name(relay: str, kind: str, phase: str) -> str:
    suffix = "A" if kind == "cur" else "V"
    return f"{relay}_{kind}_{phase}_{suffix}"


RELAY_IDS = tuple(relay for endpoints in LINE_ENDPOINTS.values() for relay in endpoints)

# The source DataFrame has one time column followed by these 48 named channels.
# The locator never consumes the time column; acquisition removes it before handoff.
CHANNEL_SCHEMA = tuple(
    channel
    for relay in RELAY_IDS
    for kind in ("cur", "vol")
    for phase in PHASES
    for channel in (_channel_name(relay, kind, phase),)
)

CURRENT_CHANNELS_BY_RELAY = {
    relay: tuple(_channel_name(relay, "cur", phase) for phase in PHASES)
    for relay in RELAY_IDS
}

CHANNEL_SCHEMA_RECORD = {
    "time_column": TIME_COLUMN,
    "sample_rate_hz": SAMPLE_RATE_HZ,
    "sample_count": SAMPLE_COUNT,
    "channels": list(CHANNEL_SCHEMA),
    "current_channels_by_relay": {
        relay: list(channels) for relay, channels in CURRENT_CHANNELS_BY_RELAY.items()
    },
}

