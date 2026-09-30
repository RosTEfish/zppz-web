"""Chart text normalization ported from MiaCode (MIT License).

Copyright (c) 2026 fanfaredash (original MiaCode ChartNormalization)
Adapted for zppz-web public package formatting.

Source reference:
https://github.com/Team-MiaCode/MiaCode
docs/specs/chart/CHART_DIAGNOSTICS_AND_NORMALIZATION_SPEC.md §3
src/core/chart/transform/ChartNormalization.cpp
src/core/chart/transform/Non384SnapTable.cpp
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import gcd

SNAP_384_MODULUS = 384
MIN_SNAP_SUBDIVISION_BEATS = 16
MAX_SNAP_SUBDIVISION_BEATS = 384
SNAP_TOLERANCE_WHOLE = (1.0 / (2.0 * MAX_SNAP_SUBDIVISION_BEATS)) + 1e-9
DEFAULT_METER_NUMERATOR = 4
DEFAULT_METER_DENOMINATOR = 4
DEFAULT_BEATS = 4
DEFAULT_BPM = 120.0
SLIDE_OPS = "-^v<>Vpqszw"
_DIVISORS_OF_384 = tuple(d for d in range(1, SNAP_384_MODULUS + 1) if SNAP_384_MODULUS % d == 0)


def qround(value: float) -> int:
    """Match Qt qRound / qRound64 half-away-from-zero for positive and negative."""
    if value >= 0:
        return int(value + 0.5)
    return int(value - 0.5)


def qbound(low: int, value: int, high: int) -> int:
    return max(low, min(high, value))


@dataclass
class Rational:
    numerator: int = 0
    denominator: int = 1

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> None:
        if self.denominator == 0:
            self.numerator = 0
            self.denominator = 1
            return
        if self.denominator < 0:
            self.numerator = -self.numerator
            self.denominator = -self.denominator
        if self.numerator == 0:
            self.denominator = 1
            return
        g = gcd(abs(self.numerator), self.denominator)
        if g > 1:
            self.numerator //= g
            self.denominator //= g

    def is_zero(self) -> bool:
        return self.numerator == 0

    def copy(self) -> Rational:
        return Rational(self.numerator, self.denominator)


def _add(left: Rational, right: Rational) -> Rational:
    return Rational(
        left.numerator * right.denominator + right.numerator * left.denominator,
        left.denominator * right.denominator,
    )


def _sub(left: Rational, right: Rational) -> Rational:
    return Rational(
        left.numerator * right.denominator - right.numerator * left.denominator,
        left.denominator * right.denominator,
    )


def _lt(left: Rational, right: Rational) -> bool:
    return left.numerator * right.denominator < right.numerator * left.denominator


def _le(left: Rational, right: Rational) -> bool:
    return not _lt(right, left)


def _ge(left: Rational, right: Rational) -> bool:
    return not _lt(left, right)


def _eq(left: Rational, right: Rational) -> bool:
    return left.numerator == right.numerator and left.denominator == right.denominator


def to_double(value: Rational) -> float:
    return value.numerator / value.denominator


def safe_lcm(left: int, right: int) -> int:
    if left <= 0:
        return max(1, right)
    if right <= 0:
        return max(1, left)
    g = gcd(left, right)
    scaled = left // g
    if scaled > (2**63 - 1) // right:
        return 0
    return scaled * right


def scale_rational_exact(value: Rational, scale: int) -> tuple[bool, int]:
    if scale <= 0:
        return False, 0
    scaled_numerator = value.numerator * scale
    if scaled_numerator % value.denominator != 0:
        return False, 0
    return True, scaled_numerator // value.denominator


def scale_rational_rounded(value: Rational, scale: int) -> int:
    return qround(to_double(value) * scale)


def scaled_snap_error(value: Rational, scaled_value: int, scale: int) -> float:
    return abs(to_double(value) - (scaled_value / scale))


@dataclass
class SnapResult:
    ok: bool = False
    p: int = 0
    q: int = 1


def _round_div_positive(num: int, den: int) -> int:
    return (num + den // 2) // den


def _largest_divisor_of_384_at_most(cap: int) -> int:
    chosen = 0
    for q in _DIVISORS_OF_384:
        if q <= cap:
            chosen = q
        else:
            break
    return chosen


def snap_x_over_y(x: int, y: int) -> SnapResult:
    if y <= 0:
        return SnapResult(False, 0, 0)
    if SNAP_384_MODULUS % y == 0:
        return SnapResult(True, x, y)
    if y > SNAP_384_MODULUS:
        p = _round_div_positive(SNAP_384_MODULUS * x, y)
        return SnapResult(True, p, SNAP_384_MODULUS)
    chosen_q = _largest_divisor_of_384_at_most(4 * y)
    if chosen_q <= 0:
        return SnapResult(False, 0, 0)
    p = _round_div_positive(chosen_q * x, y)
    return SnapResult(True, p, chosen_q)


@dataclass
class ChartNormalizationOptions:
    start_at_new_measure: bool = True
    reduce_to_384_grid: bool = True


@dataclass
class ChartNormalizationResult:
    ok: bool = False
    text: str = ""
    error_message: str = ""
    changed_count: int = 0
    measure_line_count: int = 0


@dataclass
class SimaiTimingMetadata:
    whole_time_signature_text: str = ""
    whole_time_signature_numerator: int = DEFAULT_METER_NUMERATOR
    whole_time_signature_denominator: int = DEFAULT_METER_DENOMINATOR
    whole_time_signature_valid: bool = False


class BoundaryItemKind(Enum):
    STANDALONE_TEXT = 0
    BPM = 1
    TIME_SIGNATURE = 2


@dataclass
class BoundaryItem:
    kind: BoundaryItemKind = BoundaryItemKind.STANDALONE_TEXT
    text: str = ""


MomentGroups = list[list[str]]


@dataclass
class MeasureMoment:
    position_whole: Rational
    groups: MomentGroups


@dataclass
class MeasureBuilder:
    meter_numerator: int = DEFAULT_METER_NUMERATOR
    meter_denominator: int = DEFAULT_METER_DENOMINATOR
    start_phase_whole: Rational = field(default_factory=Rational)
    leading_items: list[BoundaryItem] = field(default_factory=list)
    trailing_items: list[BoundaryItem] = field(default_factory=list)
    moments: list[MeasureMoment] = field(default_factory=list)


@dataclass
class RenderMeasure:
    meter_numerator: int = DEFAULT_METER_NUMERATOR
    meter_denominator: int = DEFAULT_METER_DENOMINATOR
    start_phase_whole: Rational = field(default_factory=Rational)
    length_whole: Rational = field(default_factory=Rational)
    leading_items: list[BoundaryItem] = field(default_factory=list)
    trailing_items: list[BoundaryItem] = field(default_factory=list)
    moments: list[MeasureMoment] = field(default_factory=list)


@dataclass
class NormalizationSeed:
    meter_numerator: int = DEFAULT_METER_NUMERATOR
    meter_denominator: int = DEFAULT_METER_DENOMINATOR
    start_phase_whole: Rational = field(default_factory=Rational)
    current_beats: int = DEFAULT_BEATS
    current_bpm: float = DEFAULT_BPM


@dataclass
class TouchTokenParts:
    prefix: str = ""
    bracket_suffix: str = ""
    has_hold: bool = False
    has_break: bool = False
    has_ex: bool = False
    has_firework: bool = False
    valid: bool = False


@dataclass
class NoteTokenParts:
    lane: str = ""
    bracket_suffix: str = ""
    extra_modifiers: str = ""
    has_hold: bool = False
    has_break: bool = False
    has_ex: bool = False
    valid: bool = False


@dataclass
class SlideSegmentParts:
    text: str = ""
    segment_break: bool = False


@dataclass
class SlideTokenParts:
    lane: str = ""
    head_extra_modifiers: str = ""
    head_break: bool = False
    head_ex: bool = False
    segments: list[SlideSegmentParts] = field(default_factory=list)
    valid: bool = False


@dataclass
class DurationNormalizationOptions:
    allow_zero_duration: bool = False
    omit_zero_duration_bracket: bool = False


def normalize_time_signature_text(numerator: int, denominator: int) -> str:
    return f"{max(1, numerator)}/{max(1, denominator)}"


def parse_time_signature_text(text: str) -> tuple[bool, int, int, str]:
    import re

    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
    if not match:
        return False, 0, 0, ""
    numerator = int(match.group(1))
    denominator = int(match.group(2))
    if numerator <= 0 or denominator <= 0:
        return False, 0, 0, ""
    normalized = f"{numerator}/{denominator}"
    return True, numerator, denominator, normalized


def parse_inline_time_signature_comment(
    line: str, comment_start_index: int
) -> tuple[bool, int, int, str]:
    if comment_start_index < 0 or comment_start_index + 1 >= len(line):
        return False, 0, 0, ""
    if line[comment_start_index] != "|" or line[comment_start_index + 1] != "|":
        return False, 0, 0, ""
    index = comment_start_index
    while index + 1 < len(line) and line[index : index + 2] == "||":
        index += 2
        while index < len(line) and line[index].isspace():
            index += 1
        if index + 1 >= len(line) or line[index : index + 2] != "||":
            break
    return parse_time_signature_text(line[index:])


def is_digit_lane(ch: str) -> bool:
    return len(ch) == 1 and "1" <= ch <= "8"


def is_simple_digit_cluster(token: str) -> bool:
    if len(token) <= 1:
        return False
    return all(is_digit_lane(ch) for ch in token)


def is_slide_operator_char(ch: str) -> bool:
    return ch in SLIDE_OPS


def has_slide_operator(token: str) -> bool:
    return any(is_slide_operator_char(ch) for ch in token)


def touch_prefix_length(token: str) -> int:
    if not token:
        return 0
    head = token[0].upper()
    if head == "C":
        if len(token) >= 2 and token[1] in ("1", "2"):
            return 2
        return 1
    if (
        len(token) >= 2
        and head in ("A", "B", "D", "E")
        and is_digit_lane(token[1])
    ):
        return 2
    return 0


def sorted_modifier_text(modifiers: str) -> str:
    return "".join(sorted(modifiers, key=ord))


def parse_plain_duration_signature(signature: str) -> tuple[bool, Rational]:
    if "#" in signature:
        return False, Rational()
    colon = signature.find(":")
    if colon < 0 or signature.find(":", colon + 1) >= 0:
        return False, Rational()
    left = signature[:colon].strip()
    right = signature[colon + 1 :].strip()
    try:
        beats = int(left)
        numerator = int(right)
    except ValueError:
        return False, Rational()
    if beats <= 0 or numerator < 0:
        return False, Rational()
    return True, Rational(numerator, beats)


def normalize_plain_duration_signature(
    signature: str,
    _grid_beats: int,
    reduce_to_384_grid: bool,
    options: DurationNormalizationOptions,
) -> str:
    ok, _duration = parse_plain_duration_signature(signature)
    if not ok:
        return signature
    if not reduce_to_384_grid:
        return signature
    colon = signature.find(":")
    try:
        original_beats = int(signature[:colon].strip())
        original_numerator = int(signature[colon + 1 :].strip())
    except ValueError:
        return signature
    if original_beats <= 0 or original_numerator < 0:
        return signature
    if SNAP_384_MODULUS % original_beats == 0:
        return signature
    snap = snap_x_over_y(original_numerator, original_beats)
    if not snap.ok:
        return signature
    if snap.p == 0:
        if not options.allow_zero_duration:
            return f"{snap.q}:1"
        if options.omit_zero_duration_bracket:
            return ""
        return "1:0"
    return f"{snap.q}:{snap.p}"


def normalize_single_bracket_suffix(
    bracket_suffix: str,
    grid_beats: int,
    reduce_to_384_grid: bool,
    options: DurationNormalizationOptions,
) -> str:
    if not bracket_suffix:
        return ""
    open_bracket = bracket_suffix.find("[")
    close_bracket = bracket_suffix.rfind("]")
    if open_bracket < 0 or close_bracket != len(bracket_suffix) - 1:
        return bracket_suffix
    normalized_signature = normalize_plain_duration_signature(
        bracket_suffix[open_bracket + 1 : close_bracket],
        grid_beats,
        reduce_to_384_grid,
        options,
    )
    if not normalized_signature:
        return ""
    return f"[{normalized_signature}]"


def parse_touch_token_parts(token: str) -> TouchTokenParts | None:
    parts = TouchTokenParts()
    prefix_length = touch_prefix_length(token)
    if prefix_length <= 0 or prefix_length > len(token):
        return None
    suffix = token[prefix_length:]
    open_bracket = suffix.find("[")
    close_bracket = suffix.rfind("]")
    if (open_bracket < 0) != (close_bracket < 0):
        return None
    if open_bracket >= 0 and close_bracket != len(suffix) - 1:
        return None
    parts.prefix = token[:prefix_length]
    parts.bracket_suffix = suffix[open_bracket:] if open_bracket >= 0 else ""
    modifier_part = suffix[:open_bracket] if open_bracket >= 0 else suffix
    for ch in modifier_part:
        lower = ch.lower()
        if lower == "b":
            parts.has_break = True
        elif lower == "x":
            parts.has_ex = True
        elif lower == "f":
            parts.has_firework = True
        elif lower == "h":
            parts.has_hold = True
        elif not ch.isspace():
            return None
    if parts.bracket_suffix:
        if not parts.has_hold:
            return None
    elif parts.has_hold:
        return None
    parts.valid = True
    return parts


def parse_note_token_parts(token: str) -> NoteTokenParts | None:
    parts = NoteTokenParts()
    if not token or not is_digit_lane(token[0]) or has_slide_operator(token) or is_simple_digit_cluster(token):
        return None
    open_bracket = token.find("[")
    close_bracket = token.rfind("]")
    if (open_bracket < 0) != (close_bracket < 0):
        return None
    if open_bracket >= 0 and close_bracket != len(token) - 1:
        return None
    core = token[:open_bracket] if open_bracket >= 0 else token
    if not core or not is_digit_lane(core[0]):
        return None
    parts.lane = core[0]
    parts.bracket_suffix = token[open_bracket:] if open_bracket >= 0 else ""
    extras: list[str] = []
    for ch in core[1:]:
        lower = ch.lower()
        if lower == "b":
            parts.has_break = True
        elif lower == "x":
            parts.has_ex = True
        elif lower == "h":
            parts.has_hold = True
        elif not ch.isspace():
            extras.append(ch)
    parts.extra_modifiers = "".join(extras)
    if parts.bracket_suffix and not parts.has_hold:
        return None
    if not parts.bracket_suffix and parts.has_hold:
        return None
    parts.valid = True
    return parts


def parse_slide_token_parts(token: str) -> SlideTokenParts | None:
    parts = SlideTokenParts()
    if not token or not is_digit_lane(token[0]) or not has_slide_operator(token):
        return None
    parts.lane = token[0]
    prefix_length = 0
    while 1 + prefix_length < len(token):
        ch = token[1 + prefix_length]
        lower = ch.lower()
        if lower == "b":
            parts.head_break = True
            prefix_length += 1
            continue
        if lower == "x":
            parts.head_ex = True
            prefix_length += 1
            continue
        if lower == "h":
            return None
        if ch in ("@", "?", "!"):
            parts.head_extra_modifiers += ch
            prefix_length += 1
            continue
        break
    remainder = token[1 + prefix_length :]
    if not remainder:
        return None
    for raw in remainder.split("*"):
        seg = SlideSegmentParts()
        chars: list[str] = []
        for ch in raw:
            if ch.lower() == "b":
                seg.segment_break = True
                continue
            chars.append(ch)
        seg.text = "".join(chars)
        parts.segments.append(seg)
    if not parts.segments:
        return None
    parts.valid = True
    return parts


def build_touch_token(parts: TouchTokenParts) -> str:
    token = parts.prefix
    if parts.has_break:
        token += "b"
    if parts.has_ex:
        token += "x"
    if parts.has_hold:
        token += "h"
    if parts.has_firework:
        token += "f"
    token += parts.bracket_suffix
    return token


def build_note_token(parts: NoteTokenParts) -> str:
    token = parts.lane
    token += sorted_modifier_text(parts.extra_modifiers)
    if parts.has_break:
        token += "b"
    if parts.has_ex:
        token += "x"
    if parts.has_hold:
        token += "h"
    token += parts.bracket_suffix
    return token


def build_slide_token(parts: SlideTokenParts) -> str:
    token = parts.lane
    token += sorted_modifier_text(parts.head_extra_modifiers)
    if parts.head_break:
        token += "b"
    if parts.head_ex:
        token += "x"
    for index, seg in enumerate(parts.segments):
        if index > 0:
            token += "*"
        seg_text = seg.text
        if seg.segment_break:
            first_bracket = seg_text.find("[")
            if first_bracket >= 0:
                seg_text = seg_text[:first_bracket] + "b" + seg_text[first_bracket:]
            else:
                seg_text += "b"
        token += seg_text
    return token


def canonicalize_token(token: str) -> str:
    trimmed = token.strip()
    if not trimmed:
        return ""
    touch = parse_touch_token_parts(trimmed)
    if touch and touch.valid:
        return build_touch_token(touch)
    note = parse_note_token_parts(trimmed)
    if note and note.valid:
        return build_note_token(note)
    slide = parse_slide_token_parts(trimmed)
    if slide and slide.valid:
        return build_slide_token(slide)
    return trimmed


def render_token_for_grid(token: str, grid_beats: int, reduce_to_384_grid: bool) -> str:
    trimmed = token.strip()
    if not trimmed:
        return ""
    touch = parse_touch_token_parts(trimmed)
    if touch and touch.valid:
        touch.bracket_suffix = normalize_single_bracket_suffix(
            touch.bracket_suffix,
            grid_beats,
            reduce_to_384_grid,
            DurationNormalizationOptions(True, False),
        )
        return build_touch_token(touch)
    note = parse_note_token_parts(trimmed)
    if note and note.valid:
        note.bracket_suffix = normalize_single_bracket_suffix(
            note.bracket_suffix,
            grid_beats,
            reduce_to_384_grid,
            DurationNormalizationOptions(True, True),
        )
        return build_note_token(note)
    slide = parse_slide_token_parts(trimmed)
    if slide and slide.valid:
        for seg in slide.segments:
            open_bracket = seg.text.find("[")
            if open_bracket >= 0:
                normalized_bracket = normalize_single_bracket_suffix(
                    seg.text[open_bracket:],
                    grid_beats,
                    reduce_to_384_grid,
                    DurationNormalizationOptions(False, False),
                )
                seg.text = seg.text[:open_bracket] + normalized_bracket
        return build_slide_token(slide)
    return trimmed


def normalized_moment_groups(groups: MomentGroups) -> MomentGroups:
    normalized: MomentGroups = []
    for group in groups:
        rendered = [token.strip() for token in group if token.strip()]
        if rendered:
            normalized.append(rendered)
    return normalized


def append_moment_groups(target: MomentGroups, extra: MomentGroups) -> None:
    for group in extra:
        if group:
            target.append(group)


def build_moment_text(groups: MomentGroups, grid_beats: int, reduce_to_384_grid: bool) -> str:
    rendered_groups: list[str] = []
    for group in groups:
        rendered_tokens = [
            rendered
            for token in group
            if (rendered := render_token_for_grid(token, grid_beats, reduce_to_384_grid))
        ]
        if rendered_tokens:
            rendered_groups.append("/".join(rendered_tokens))
    return "`".join(rendered_groups)


def is_terminal_marker_text(text: str) -> bool:
    return text.strip().lower() == "e"


def line_tail_is_terminal_marker(line: str, start_index: int) -> bool:
    if start_index < 0 or start_index >= len(line):
        return False
    tail = line[start_index:]
    comment_index = tail.find("||")
    if comment_index >= 0:
        tail = tail[:comment_index]
    return is_terminal_marker_text(tail)


def following_text_redefines_beats_before_use(remainder: str) -> bool:
    for ch in remainder:
        if ch == "{":
            return True
        if ch == ",":
            return False
    return False


def measure_length_whole(meter_numerator: int, meter_denominator: int) -> Rational:
    return Rational(max(1, meter_numerator), max(1, meter_denominator))


def normalize_measure_phase_whole(
    phase_whole: Rational, meter_numerator: int, meter_denominator: int
) -> Rational:
    measure_length = measure_length_whole(meter_numerator, meter_denominator)
    normalized = phase_whole.copy()
    while _ge(normalized, measure_length):
        normalized = _sub(normalized, measure_length)
    while _lt(normalized, Rational(0, 1)):
        normalized = _add(normalized, measure_length)
    return normalized


def append_boundary_items(lines: list[str], items: list[BoundaryItem]) -> None:
    index = 0
    while index < len(items):
        item = items[index]
        if item.kind in (BoundaryItemKind.BPM, BoundaryItemKind.TIME_SIGNATURE):
            bpm_text = item.text if item.kind == BoundaryItemKind.BPM else ""
            time_signature_text = item.text if item.kind == BoundaryItemKind.TIME_SIGNATURE else ""
            consumed = 1
            if index + 1 < len(items):
                nxt = items[index + 1]
                complementary = (
                    item.kind == BoundaryItemKind.BPM and nxt.kind == BoundaryItemKind.TIME_SIGNATURE
                ) or (
                    item.kind == BoundaryItemKind.TIME_SIGNATURE and nxt.kind == BoundaryItemKind.BPM
                )
                if complementary:
                    if nxt.kind == BoundaryItemKind.BPM:
                        bpm_text = nxt.text
                    else:
                        time_signature_text = nxt.text
                    consumed = 2
            if bpm_text and time_signature_text:
                lines.append(f"{bpm_text} {time_signature_text}")
            elif bpm_text:
                lines.append(bpm_text)
            elif time_signature_text:
                lines.append(time_signature_text)
            index += consumed
            continue
        lines.append(item.text)
        index += 1


def render_measure_line_approximate(measure: RenderMeasure) -> str:
    measure_grid_length = max(1, qround(to_double(measure.length_whole) * 384.0))
    start_phase_grid = max(0, qround(to_double(measure.start_phase_whole) * 384.0))
    end_phase_grid = start_phase_grid + measure_grid_length
    beat_grid = (
        max(1, qround(384.0 / measure.meter_denominator)) if measure.meter_denominator > 0 else 0
    )

    moment_absolute_grids = [
        start_phase_grid
        + qbound(0, qround(to_double(moment.position_whole) * 384.0), measure_grid_length)
        for moment in measure.moments
    ]

    line = ""
    last_segment_beats = 0
    segment_start_grid = start_phase_grid
    while segment_start_grid < end_phase_grid:
        segment_end_grid = end_phase_grid
        if beat_grid > 0:
            next_beat_index = (segment_start_grid // beat_grid) + 1
            segment_end_grid = min(end_phase_grid, next_beat_index * beat_grid)
        segment_length_grid = max(1, segment_end_grid - segment_start_grid)

        segment_moment_positions: list[Rational] = []
        segment_moment_indices: list[int] = []
        for index, absolute_grid in enumerate(moment_absolute_grids):
            if absolute_grid < segment_start_grid or absolute_grid >= segment_end_grid:
                continue
            segment_moment_positions.append(Rational(absolute_grid - segment_start_grid, 384))
            segment_moment_indices.append(index)

        segment_q = 0
        for moment_index in segment_moment_indices:
            moment = measure.moments[moment_index]
            snap = snap_x_over_y(int(moment.position_whole.numerator), int(moment.position_whole.denominator))
            if not snap.ok or snap.q <= 0:
                continue
            segment_q = snap.q if segment_q == 0 else safe_lcm(segment_q, snap.q)
            if segment_q <= 0 or segment_q > SNAP_384_MODULUS:
                segment_q = SNAP_384_MODULUS
                break
        if segment_q == 0:
            segment_q = 1
        if segment_q <= 16 and 16 % segment_q == 0:
            segment_q = 16
        if measure.meter_denominator > 0:
            aligned = safe_lcm(segment_q, measure.meter_denominator)
            if aligned > 0 and aligned <= SNAP_384_MODULUS and SNAP_384_MODULUS % aligned == 0:
                segment_q = aligned
            else:
                segment_q = SNAP_384_MODULUS
        beats = int(segment_q)

        slot_count = max(1, qround(to_double(Rational(segment_length_grid, 384)) * beats))
        slot_groups: list[MomentGroups] = [[] for _ in range(slot_count)]
        for local_index, moment_index in enumerate(segment_moment_indices):
            scaled = scale_rational_rounded(segment_moment_positions[local_index], beats)
            slot_index = qbound(0, int(scaled), slot_count - 1)
            append_moment_groups(slot_groups[slot_index], measure.moments[moment_index].groups)

        if not line or beats != last_segment_beats:
            line += f"{{{beats}}}"
            last_segment_beats = beats
        for slot_group in slot_groups:
            line += build_moment_text(slot_group, beats, True)
            line += ","
        if segment_end_grid < end_phase_grid and beat_grid > 0 and segment_end_grid % beat_grid == 0:
            line += " "
        segment_start_grid = segment_end_grid

    return line.strip()


def beat_boundary_positions(measure: RenderMeasure) -> list[Rational]:
    boundaries: list[Rational] = []
    beat_length = Rational(1, max(1, measure.meter_denominator))
    absolute_start = measure.start_phase_whole
    absolute_end = _add(measure.start_phase_whole, measure.length_whole)
    beat_index = (absolute_start.numerator * beat_length.denominator) // (
        absolute_start.denominator * beat_length.numerator
    )
    candidate = Rational((beat_index + 1) * beat_length.numerator, beat_length.denominator)
    while _lt(candidate, absolute_end):
        boundaries.append(_sub(candidate, absolute_start))
        candidate = _add(candidate, beat_length)
    return boundaries


def choose_exact_beats_for_range(measure: RenderMeasure, start: Rational, end: Rational) -> int:
    beats = 1
    chunk_length = _sub(end, start)
    beats = safe_lcm(beats, chunk_length.denominator)
    if beats <= 0:
        return 0
    for moment in measure.moments:
        if _lt(moment.position_whole, start) or _ge(moment.position_whole, end):
            continue
        relative = _sub(moment.position_whole, start)
        beats = safe_lcm(beats, relative.denominator)
        if beats <= 0 or beats > 2**31 - 1:
            return 0
    return max(1, int(beats))


def render_exact_chunk(measure: RenderMeasure, start: Rational, end: Rational, beats: int) -> str:
    ok, slot_count64 = scale_rational_exact(_sub(end, start), beats)
    if not ok or slot_count64 <= 0:
        return ""
    slot_count = min(slot_count64, 2**31 - 1)
    slot_groups: list[MomentGroups] = [[] for _ in range(slot_count)]
    for moment in measure.moments:
        if _lt(moment.position_whole, start) or _ge(moment.position_whole, end):
            continue
        exact_ok, scaled = scale_rational_exact(_sub(moment.position_whole, start), beats)
        if not exact_ok:
            continue
        slot_index = qbound(0, int(scaled), slot_count - 1)
        append_moment_groups(slot_groups[slot_index], moment.groups)
    text = f"{{{beats}}}"
    for slot_group in slot_groups:
        text += build_moment_text(slot_group, beats, False)
        text += ","
    return text


def render_measure_line_exact(measure: RenderMeasure) -> str:
    line = ""
    last_beats = 0
    cursor = Rational(0, 1)
    boundaries = beat_boundary_positions(measure)
    boundary_index = 0

    while _lt(cursor, measure.length_whole):
        chosen_end = measure.length_whole.copy()
        chosen_ends_at_beat_boundary = False
        chosen_beats = 0

        candidates: list[tuple[Rational, bool]] = []
        for index in range(boundary_index, len(boundaries)):
            if _le(boundaries[index], cursor):
                continue
            candidates.append((boundaries[index], True))
        candidates.append((measure.length_whole, False))

        minimal_beats = 2**31 - 1
        for candidate_end, ends_at_boundary in candidates:
            candidate_beats = choose_exact_beats_for_range(measure, cursor, candidate_end)
            if candidate_beats <= 0:
                continue
            if candidate_beats < minimal_beats:
                minimal_beats = candidate_beats
                chosen_end = candidate_end
                chosen_ends_at_beat_boundary = ends_at_boundary
                chosen_beats = candidate_beats

        if chosen_beats <= 0:
            break

        chunk_text = render_exact_chunk(measure, cursor, chosen_end, chosen_beats)
        if not chunk_text:
            break
        if not line or chosen_beats != last_beats:
            line += chunk_text
        else:
            line += chunk_text[chunk_text.find("}") + 1 :]
        last_beats = chosen_beats

        if chosen_ends_at_beat_boundary and _lt(chosen_end, measure.length_whole):
            line += " "
        cursor = chosen_end
        while boundary_index < len(boundaries) and _le(boundaries[boundary_index], cursor):
            boundary_index += 1

    return line.strip()


def render_measure_line(measure: RenderMeasure, options: ChartNormalizationOptions) -> str:
    if not options.reduce_to_384_grid:
        for moment in measure.moments:
            denom = moment.position_whole.denominator
            if denom > 0 and MAX_SNAP_SUBDIVISION_BEATS % denom != 0:
                return render_measure_line_exact(measure)
    return render_measure_line_approximate(measure)


def seed_from_timing_metadata(timing_metadata: SimaiTimingMetadata | None = None) -> NormalizationSeed:
    seed = NormalizationSeed()
    if timing_metadata and timing_metadata.whole_time_signature_valid:
        seed.meter_numerator = timing_metadata.whole_time_signature_numerator
        seed.meter_denominator = timing_metadata.whole_time_signature_denominator
    return seed


def scan_normalization_seed(
    prefix: str, timing_metadata: SimaiTimingMetadata | None = None
) -> NormalizationSeed:
    seed = seed_from_timing_metadata(timing_metadata)
    current_phase = Rational()

    def advance_by_comma() -> None:
        nonlocal current_phase
        current_phase = _add(current_phase, Rational(1, max(1, seed.current_beats)))
        measure_length = measure_length_whole(seed.meter_numerator, seed.meter_denominator)
        while _ge(current_phase, measure_length):
            current_phase = _sub(current_phase, measure_length)

    for raw_line in prefix.split("\n"):
        line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        if is_terminal_marker_text(line):
            break
        index = 0
        while index < len(line):
            ch = line[index]
            if ch == "|" and index + 1 < len(line) and line[index + 1] == "|":
                ok, numerator, denominator, _ = parse_inline_time_signature_comment(line, index)
                if ok:
                    seed.meter_numerator = max(1, numerator)
                    seed.meter_denominator = max(1, denominator)
                    current_phase = Rational()
                break
            if ch.isspace() or ch == "/":
                index += 1
                continue
            if ch == "(":
                close = line.find(")", index + 1)
                if close < 0:
                    break
                bpm_text = line[index + 1 : close].strip()
                try:
                    parsed_bpm = float(bpm_text)
                except ValueError:
                    parsed_bpm = None
                if parsed_bpm is not None:
                    seed.current_bpm = parsed_bpm
                    current_phase = Rational()
                index = close + 1
                continue
            if ch == "{":
                close = line.find("}", index + 1)
                if close < 0:
                    break
                beats_text = line[index + 1 : close].strip()
                try:
                    parsed_beats = int(beats_text)
                except ValueError:
                    parsed_beats = 0
                if parsed_beats > 0:
                    seed.current_beats = parsed_beats
                index = close + 1
                continue
            if ch == "<" and line[index : index + 4] == "<HS*":
                close = line.find(">", index + 4)
                if close < 0:
                    break
                index = close + 1
                continue
            if ch == "`":
                index += 1
                continue
            if ch == ",":
                advance_by_comma()
                index += 1
                continue
            if ch in ("E", "e") and line_tail_is_terminal_marker(line, index):
                break
            index += 1

    seed.start_phase_whole = normalize_measure_phase_whole(
        current_phase, seed.meter_numerator, seed.meter_denominator
    )
    return seed


def normalize_chart_fragment(
    input_text: str,
    seed: NormalizationSeed,
    options: ChartNormalizationOptions | None = None,
    *,
    append_terminal_marker: bool = True,
    inject_leading_time_signature: bool = False,
    append_trailing_beats_marker: bool = True,
) -> ChartNormalizationResult:
    options = options or ChartNormalizationOptions()
    result = ChartNormalizationResult()

    rendered_measures: list[RenderMeasure] = []
    current_measure = MeasureBuilder(
        meter_numerator=seed.meter_numerator,
        meter_denominator=seed.meter_denominator,
        start_phase_whole=Rational() if options.start_at_new_measure else seed.start_phase_whole.copy(),
    )
    if inject_leading_time_signature:
        current_measure.leading_items.append(
            BoundaryItem(
                BoundaryItemKind.TIME_SIGNATURE,
                f"|| {normalize_time_signature_text(seed.meter_numerator, seed.meter_denominator)}",
            )
        )

    current_position_whole = Rational()
    current_beats = max(1, seed.current_beats)
    current_bpm = seed.current_bpm
    token = ""
    current_group_tokens: list[str] = []
    current_groups: list[list[str]] = []

    def flush_token() -> None:
        nonlocal token
        if not token:
            return
        canonical = canonicalize_token(token)
        if canonical:
            current_group_tokens.append(canonical)
        token = ""

    def finalize_group() -> None:
        nonlocal current_group_tokens
        if current_group_tokens:
            current_groups.append(current_group_tokens)
            current_group_tokens = []

    def flush_moment() -> None:
        nonlocal current_groups
        flush_token()
        finalize_group()
        groups = normalized_moment_groups(current_groups)
        if groups:
            current_measure.moments.append(
                MeasureMoment(position_whole=current_position_whole.copy(), groups=groups)
            )
        current_groups = []

    def append_rendered_measure(length_whole: Rational) -> None:
        if (
            length_whole.is_zero()
            and not current_measure.leading_items
            and not current_measure.trailing_items
            and not current_measure.moments
        ):
            return
        rendered_measures.append(
            RenderMeasure(
                meter_numerator=current_measure.meter_numerator,
                meter_denominator=current_measure.meter_denominator,
                start_phase_whole=current_measure.start_phase_whole.copy(),
                length_whole=length_whole.copy(),
                leading_items=list(current_measure.leading_items),
                trailing_items=list(current_measure.trailing_items),
                moments=list(current_measure.moments),
            )
        )

    def begin_fresh_measure(
        meter_numerator: int,
        meter_denominator: int,
        start_phase_whole: Rational | None = None,
    ) -> None:
        nonlocal current_measure, current_position_whole
        start_phase = start_phase_whole or Rational()
        current_measure = MeasureBuilder(
            meter_numerator=max(1, meter_numerator),
            meter_denominator=max(1, meter_denominator),
            start_phase_whole=normalize_measure_phase_whole(
                start_phase, max(1, meter_numerator), max(1, meter_denominator)
            ),
        )
        current_position_whole = Rational()

    def current_remaining_measure_length() -> Rational:
        return _sub(
            measure_length_whole(current_measure.meter_numerator, current_measure.meter_denominator),
            current_measure.start_phase_whole,
        )

    def append_boundary_item(item: BoundaryItem) -> None:
        flush_moment()
        if current_measure.moments or not current_position_whole.is_zero():
            current_measure.trailing_items.append(item)
            return
        current_measure.leading_items.append(item)

    def restart_measure_at_current_position(
        item: BoundaryItem, next_meter_numerator: int, next_meter_denominator: int
    ) -> None:
        flush_moment()
        if current_measure.moments or not current_position_whole.is_zero():
            append_rendered_measure(current_position_whole.copy())
            begin_fresh_measure(next_meter_numerator, next_meter_denominator)
        else:
            current_measure.meter_numerator = max(1, next_meter_numerator)
            current_measure.meter_denominator = max(1, next_meter_denominator)
            current_measure.start_phase_whole = Rational()
        current_measure.leading_items.append(item)

    def split_measure_at_current_position(item: BoundaryItem) -> None:
        flush_moment()
        if current_measure.moments or not current_position_whole.is_zero():
            carry_num = current_measure.meter_numerator
            carry_den = current_measure.meter_denominator
            next_start = _add(current_measure.start_phase_whole, current_position_whole)
            append_rendered_measure(current_position_whole.copy())
            begin_fresh_measure(carry_num, carry_den, next_start)
        current_measure.leading_items.append(item)

    def advance_by_comma() -> None:
        nonlocal current_position_whole
        flush_moment()
        current_position_whole = _add(current_position_whole, Rational(1, max(1, current_beats)))
        while _ge(current_position_whole, current_remaining_measure_length()):
            carry_num = current_measure.meter_numerator
            carry_den = current_measure.meter_denominator
            completed = current_remaining_measure_length()
            overflow = _sub(current_position_whole, completed)
            append_rendered_measure(completed)
            begin_fresh_measure(carry_num, carry_den)
            current_position_whole = overflow

    for raw_line in input_text.split("\n"):
        line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        if is_terminal_marker_text(line):
            finalize_group()
            continue

        terminated_by_comment = False
        index = 0
        while index < len(line):
            ch = line[index]

            if ch == "|" and index + 1 < len(line) and line[index + 1] == "|":
                flush_token()
                finalize_group()
                ok, numerator, denominator, normalized_text = parse_inline_time_signature_comment(
                    line, index
                )
                if ok:
                    restart_measure_at_current_position(
                        BoundaryItem(BoundaryItemKind.TIME_SIGNATURE, f"|| {normalized_text}"),
                        numerator,
                        denominator,
                    )
                else:
                    split_measure_at_current_position(
                        BoundaryItem(BoundaryItemKind.STANDALONE_TEXT, line[index:].strip())
                    )
                terminated_by_comment = True
                break

            if ch.isspace():
                flush_token()
                index += 1
                continue

            if ch == "(":
                flush_token()
                finalize_group()
                close = line.find(")", index + 1)
                if close < 0:
                    break
                bpm_text = line[index + 1 : close].strip()
                try:
                    parsed_bpm = float(bpm_text)
                except ValueError:
                    parsed_bpm = None
                if parsed_bpm is not None:
                    restart_measure_at_current_position(
                        BoundaryItem(BoundaryItemKind.BPM, f"({bpm_text})"),
                        current_measure.meter_numerator,
                        current_measure.meter_denominator,
                    )
                    current_bpm = parsed_bpm
                index = close + 1
                continue

            if ch == "{":
                flush_token()
                finalize_group()
                close = line.find("}", index + 1)
                if close < 0:
                    break
                beats_text = line[index + 1 : close].strip()
                try:
                    parsed_beats = int(beats_text)
                except ValueError:
                    parsed_beats = 0
                if parsed_beats > 0:
                    current_beats = parsed_beats
                index = close + 1
                continue

            if ch == "<" and line[index : index + 4] == "<HS*":
                flush_token()
                finalize_group()
                close = line.find(">", index + 4)
                if close < 0:
                    break
                append_boundary_item(
                    BoundaryItem(
                        BoundaryItemKind.STANDALONE_TEXT,
                        line[index : close + 1].strip(),
                    )
                )
                index = close + 1
                continue

            if ch == "/":
                flush_token()
                index += 1
                continue

            if ch == "`":
                flush_token()
                finalize_group()
                index += 1
                continue

            if ch == ",":
                advance_by_comma()
                index += 1
                continue

            if (
                not token
                and ch in ("E", "e")
                and line_tail_is_terminal_marker(line, index)
            ):
                flush_token()
                finalize_group()
                break

            token += ch
            index += 1

        flush_token()
        if not terminated_by_comment:
            finalize_group()

    flush_moment()
    if (
        current_measure.moments
        or not current_position_whole.is_zero()
        or current_measure.leading_items
        or current_measure.trailing_items
    ):
        append_rendered_measure(current_position_whole.copy())

    output_lines: list[str] = []
    emitted_measure_lines = 0
    section_measure_index = 0
    for measure in rendered_measures:
        starts_new_section = any(
            item.kind in (BoundaryItemKind.TIME_SIGNATURE, BoundaryItemKind.BPM)
            for item in measure.leading_items
        )
        if starts_new_section:
            section_measure_index = 0
        append_boundary_items(output_lines, measure.leading_items)
        if not measure.length_whole.is_zero() or measure.moments:
            output_lines.append(render_measure_line(measure, options))
            emitted_measure_lines += 1
            section_measure_index += 1
        append_boundary_items(output_lines, measure.trailing_items)
        if section_measure_index > 0 and section_measure_index % 4 == 0:
            output_lines.append("")
    while output_lines and output_lines[-1] == "":
        output_lines.pop()

    if not append_terminal_marker and append_trailing_beats_marker:
        target_beats = max(1, current_beats)
        last_emitted_beats = -1
        for line in reversed(output_lines):
            close_brace = line.rfind("}")
            if close_brace < 0:
                continue
            open_brace = line.rfind("{", 0, close_brace)
            if open_brace < 0:
                continue
            try:
                beats = int(line[open_brace + 1 : close_brace].strip())
            except ValueError:
                continue
            if beats > 0:
                last_emitted_beats = beats
                break
        if last_emitted_beats != target_beats:
            output_lines.append(f"{{{target_beats}}}")

    if append_terminal_marker:
        output_lines.append("E")

    result.ok = True
    result.text = "\n".join(output_lines)
    result.measure_line_count = emitted_measure_lines
    result.changed_count = 0 if result.text == input_text else max(1, emitted_measure_lines)
    # Silence unused assignment lint for current_bpm (kept for parity with MiaCode).
    _ = current_bpm
    return result


def normalize_chart_text(
    input_text: str,
    timing_metadata: SimaiTimingMetadata | None = None,
    options: ChartNormalizationOptions | None = None,
) -> ChartNormalizationResult:
    return normalize_chart_fragment(
        input_text,
        seed_from_timing_metadata(timing_metadata),
        options or ChartNormalizationOptions(),
        append_terminal_marker=True,
        inject_leading_time_signature=False,
    )


def normalize_chart_selection_text(
    full_text: str,
    selection_start: int,
    selection_end: int,
    timing_metadata: SimaiTimingMetadata | None = None,
    options: ChartNormalizationOptions | None = None,
) -> ChartNormalizationResult:
    options = options or ChartNormalizationOptions()
    if (
        selection_start < 0
        or selection_end < selection_start
        or selection_end > len(full_text)
    ):
        return ChartNormalizationResult(error_message="Invalid selection range.")

    seed = scan_normalization_seed(full_text[:selection_start], timing_metadata)
    should_inject = options.start_at_new_measure and not seed.start_phase_whole.is_zero()
    if options.start_at_new_measure:
        seed.start_phase_whole = Rational()
    append_trailing = not following_text_redefines_beats_before_use(full_text[selection_end:])
    return normalize_chart_fragment(
        full_text[selection_start:selection_end],
        seed,
        options,
        append_terminal_marker=False,
        inject_leading_time_signature=should_inject,
        append_trailing_beats_marker=append_trailing,
    )
