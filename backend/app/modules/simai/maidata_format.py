"""Format maidata.txt chart bodies using MiaCode-style normalization."""

from __future__ import annotations

import re

from app.modules.simai.chart_normalization import (
    ChartNormalizationOptions,
    normalize_chart_text,
)

INOTE_PATTERN = re.compile(
    r"(^&inote_([1-7])=)(.*?)(?=^&[A-Za-z0-9_]+=|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def _decode_maidata(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "shift_jis", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("maidata.txt 编码无法识别")


def _normalize_inote_body(body: str, options: ChartNormalizationOptions) -> str:
    """Normalize one &inote_N= body; return original body on failure."""
    stripped = body.strip("\r\n")
    if not stripped.strip():
        return body

    # Charts often omit a trailing E; MiaCode whole-chart path always appends one.
    result = normalize_chart_text(stripped, options=options)
    if not result.ok or not result.text.strip():
        return body

    # Prefer a leading newline after &inote_N= when the body is multi-line.
    leading = "\n" if body.startswith(("\n", "\r\n")) or "\n" in stripped else ""
    text = result.text
    if not text.endswith("\n"):
        text += "\n"
    return f"{leading}{text}"


def format_maidata_text(
    text: str,
    *,
    options: ChartNormalizationOptions | None = None,
) -> str:
    """Rewrite every &inote_N= body into MiaCode Format Chart form."""
    opts = options or ChartNormalizationOptions()

    def replace(match: re.Match[str]) -> str:
        prefix = match.group(1)
        body = match.group(3)
        return prefix + _normalize_inote_body(body, opts)

    return INOTE_PATTERN.sub(replace, text)


def format_maidata_bytes(raw: bytes) -> bytes:
    """Decode, format inote bodies, and re-encode as UTF-8."""
    text = _decode_maidata(raw)
    formatted = format_maidata_text(text)
    return formatted.encode("utf-8")
