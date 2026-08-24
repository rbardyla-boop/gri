from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from .channel_schema import (
    CHANNEL_SCHEMA,
    CURRENT_CHANNELS_BY_RELAY,
    LINE_ENDPOINTS,
    SAMPLE_RATE_HZ,
)
from .producer_boundary import FORBIDDEN_PRODUCER_FIELDS

RMS_WINDOW_SAMPLES = 128
BASELINE_WINDOW_SAMPLES = 640
POST_WINDOW_SAMPLES = 640
ONSET_THRESHOLD = 5.0
PERSISTENCE_SAMPLES = 32
PEAK_TIE_WINDOW_SAMPLES = 128


@dataclass(frozen=True)
class ProducerInput:
    opaque_id: str
    t_evnt_start: float
    waveform_sha256: str
    channel_schema: tuple[str, ...]
    waveform: Mapping[str, Sequence[float]]

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ProducerInput":
        forbidden = sorted(set(value).intersection(FORBIDDEN_PRODUCER_FIELDS))
        if forbidden:
            raise ValueError(f"forbidden producer fields: {forbidden}")
        required = {"opaque_id", "t_evnt_start", "waveform_sha256", "channel_schema", "waveform"}
        if set(value) != required:
            raise ValueError(f"producer input schema mismatch: expected {sorted(required)}")
        schema = tuple(value["channel_schema"])  # type: ignore[arg-type]
        waveform = value["waveform"]
        if not isinstance(waveform, Mapping):
            raise ValueError("producer waveform must be a channel mapping")
        return cls(
            opaque_id=str(value["opaque_id"]),
            t_evnt_start=float(value["t_evnt_start"]),
            waveform_sha256=str(value["waveform_sha256"]),
            channel_schema=schema,
            waveform=waveform,  # type: ignore[arg-type]
        )


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("median of empty sequence")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _quantile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile of empty sequence")
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def causal_rms(values: Sequence[float], window: int = RMS_WINDOW_SAMPLES) -> list[float | None]:
    if window <= 0:
        raise ValueError("RMS window must be positive")
    result: list[float | None] = [None] * len(values)
    if len(values) < window:
        return result
    squares = [float(value) * float(value) for value in values]
    running = sum(squares[:window])
    result[window - 1] = math.sqrt(running / window)
    for index in range(window, len(values)):
        running += squares[index] - squares[index - window]
        result[index] = math.sqrt(running / window)
    return result


def robust_center_scale(values: Sequence[float]) -> tuple[float, float]:
    center = _median(values)
    deviations = [abs(value - center) for value in values]
    mad_scale = 1.4826 * _median(deviations)
    iqr_scale = (_quantile(values, 0.75) - _quantile(values, 0.25)) / 1.349
    scale = max(mad_scale, iqr_scale, 0.01 * abs(center), 1e-12)
    return center, scale


def event_sample_index(t_evnt_start: float) -> int:
    if not math.isfinite(t_evnt_start) or t_evnt_start < 0:
        raise ValueError("event time must be finite and non-negative")
    return math.ceil(t_evnt_start * SAMPLE_RATE_HZ)


def _baseline_indices(event_index: int) -> range:
    # The full causal RMS window [i-127, i] must lie inside the 640-sample
    # interval immediately preceding the first sample at/after the event.
    first = event_index - BASELINE_WINDOW_SAMPLES + RMS_WINDOW_SAMPLES - 1
    return range(first, event_index)


def _post_indices(event_index: int, length: int) -> range:
    return range(event_index, min(event_index + POST_WINDOW_SAMPLES, length))


def _standardized_series(
    signal: Sequence[float],
    event_index: int,
) -> tuple[list[float | None], list[float | None], float, float]:
    rms = causal_rms(signal)
    baseline_indices = _baseline_indices(event_index)
    if baseline_indices.start < RMS_WINDOW_SAMPLES - 1 or baseline_indices.stop > len(signal):
        raise ValueError("waveform does not contain a complete 100 ms pre-event baseline")
    baseline = [rms[index] for index in baseline_indices]
    if any(value is None for value in baseline):
        raise ValueError("baseline contains an incomplete causal RMS value")
    center, scale = robust_center_scale([float(value) for value in baseline if value is not None])
    standardized = [
        None if value is None else abs(float(value) - center) / scale
        for value in rms
    ]
    return rms, standardized, center, scale


def _first_persistent_onset(
    standardized_by_phase: Sequence[Sequence[float | None]],
    event_index: int,
    length: int,
) -> int | None:
    post = _post_indices(event_index, length)
    last_start = post.stop - PERSISTENCE_SAMPLES
    for start in range(post.start, max(post.start, last_start + 1)):
        end = start + PERSISTENCE_SAMPLES
        if end > post.stop:
            break
        if all(
            max(float(series[index]) for series in standardized_by_phase if series[index] is not None)
            >= ONSET_THRESHOLD
            for index in range(start, end)
        ):
            return start
    return None


def _max_standardized(
    standardized_by_phase: Sequence[Sequence[float | None]],
    indices: range,
) -> float:
    length = len(standardized_by_phase[0]) if standardized_by_phase else 0
    values = [
        float(series[index])
        for series in standardized_by_phase
        for index in indices
        if 0 <= index < length
        if series[index] is not None
    ]
    return max(values, default=0.0)


def _line_rank(
    line_onsets: Mapping[str, int | None],
    line_ties: Mapping[str, float],
) -> list[dict]:
    ordered = sorted(
        line_onsets,
        key=lambda line: (
            line_onsets[line] is None,
            line_onsets[line] if line_onsets[line] is not None else math.inf,
            -line_ties[line],
            line,
        ),
    )
    return [
        {"line_id": line, "onset_sample": line_onsets[line], "tie_peak": line_ties[line]}
        for line in ordered
    ]


def topology_only_ranking(active_lines: Sequence[str]) -> list[str]:
    """Explicit negative control; active-line metadata is not part of producer input."""

    allowed = set(LINE_ENDPOINTS)
    if not set(active_lines).issubset(allowed):
        raise ValueError("topology-only control received an unknown line")
    return sorted(set(active_lines))


def locate(producer_input: ProducerInput | Mapping[str, object]) -> dict:
    """Run primary and registered controls on producer input only."""

    if not isinstance(producer_input, ProducerInput):
        producer_input = ProducerInput.from_mapping(producer_input)
    if producer_input.channel_schema != CHANNEL_SCHEMA:
        raise ValueError("channel schema does not match the frozen PROTECT-90 schema")
    if set(producer_input.waveform) != set(CHANNEL_SCHEMA):
        raise ValueError("waveform channel set does not match the producer schema")
    lengths = {len(producer_input.waveform[channel]) for channel in CHANNEL_SCHEMA}
    if len(lengths) != 1:
        raise ValueError("waveform channels have different lengths")
    length = lengths.pop()
    event_index = event_sample_index(producer_input.t_evnt_start)
    if event_index + POST_WINDOW_SAMPLES > length:
        raise ValueError("waveform does not contain a complete 100 ms post-event window")

    relay_data: dict[str, dict[str, object]] = {}
    for relay, channels in CURRENT_CHANNELS_BY_RELAY.items():
        standardized_by_phase = []
        centers = {}
        scales = {}
        for channel in channels:
            _, standardized, center, scale = _standardized_series(
                producer_input.waveform[channel], event_index
            )
            standardized_by_phase.append(standardized)
            centers[channel] = center
            scales[channel] = scale
        onset = _first_persistent_onset(standardized_by_phase, event_index, length)
        relay_data[relay] = {
            "onset_sample": onset,
            "standardized_by_phase": standardized_by_phase,
            "baseline_centers": centers,
            "baseline_scales": scales,
        }

    primary_onsets: dict[str, int | None] = {}
    single_onsets: dict[str, int | None] = {}
    primary_ties: dict[str, float] = {}
    single_ties: dict[str, float] = {}
    magnitude_scores: dict[str, float] = {}
    for line, (sending, receiving) in LINE_ENDPOINTS.items():
        sending_onset = relay_data[sending]["onset_sample"]
        receiving_onset = relay_data[receiving]["onset_sample"]
        single_onsets[line] = sending_onset  # type: ignore[assignment]
        if sending_onset is None:
            single_ties[line] = 0.0
        else:
            single_ties[line] = _max_standardized(
                relay_data[sending]["standardized_by_phase"],  # type: ignore[arg-type]
                range(sending_onset, sending_onset + PEAK_TIE_WINDOW_SAMPLES),
            )

        if sending_onset is None or receiving_onset is None:
            primary_onsets[line] = None
            primary_ties[line] = 0.0
        else:
            line_onset = max(sending_onset, receiving_onset)
            primary_onsets[line] = line_onset
            primary_ties[line] = sum(
                _max_standardized(
                    relay_data[relay]["standardized_by_phase"],  # type: ignore[arg-type]
                    range(line_onset, line_onset + PEAK_TIE_WINDOW_SAMPLES),
                )
                for relay in (sending, receiving)
            )
        magnitude_scores[line] = sum(
            _max_standardized(
                relay_data[relay]["standardized_by_phase"],  # type: ignore[arg-type]
                _post_indices(event_index, length),
            )
            for relay in (sending, receiving)
        )

    magnitude_order = sorted(magnitude_scores, key=lambda line: (-magnitude_scores[line], line))
    return {
        "opaque_id": producer_input.opaque_id,
        "primary": _line_rank(primary_onsets, primary_ties),
        "single_ended": _line_rank(single_onsets, single_ties),
        "magnitude_only": [
            {"line_id": line, "magnitude_score": magnitude_scores[line]}
            for line in magnitude_order
        ],
        "protocol": {
            "event_sample_index": event_index,
            "rms_window_samples": RMS_WINDOW_SAMPLES,
            "baseline_window_samples": BASELINE_WINDOW_SAMPLES,
            "post_window_samples": POST_WINDOW_SAMPLES,
            "onset_threshold": ONSET_THRESHOLD,
            "persistence_samples": PERSISTENCE_SAMPLES,
            "primary_endpoint_rule": "later_of_two_endpoints",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.input.read_text(encoding="utf-8"))
    result = locate(value)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ERC3A_LOCATOR_PREDICTION_EMITTED", "opaque_id": result["opaque_id"]}))


if __name__ == "__main__":
    main()
