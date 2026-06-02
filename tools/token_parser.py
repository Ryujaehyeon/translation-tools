"""Range-aware Stellaris localisation token parser.

The parser walks text left-to-right and emits non-overlapping token spans. That
keeps follow-up checks from seeing fake tokens inside already parsed tokens,
such as the trailing delimiter in ``£menu_1£EHOF`` or a ``$...$`` inside a
bracket expression.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


TOKEN_TYPES = (
    "dollar_ref",
    "icon",
    "unclosed_icon",
    "bracket_expr",
    "color_code",
    "escaped_newline",
    "over_escaped_newline",
    "escaped_tab",
    "escaped_quote",
    "escaped_bs",
)

_DOLLAR_RE = re.compile(r"\$(?:[A-Za-z_@][^$\n\t]*|\d+)\$")
_CLOSED_ICON_RE = re.compile(r"£[^\s£]+£")
_UNCLOSED_ICON_RE = re.compile(r"£([A-Za-z_][A-Za-z0-9_|:-]*)(?=$|[\s§.,;:!?)\]\}\"'}])")
_BRACKET_RE = re.compile(r"\[[^\]\n]+\]")
_COLOR_RE = re.compile(r"§[A-Za-z0-9!#]")
_OVER_ESCAPED_NL_RE = re.compile(r"\\{2,}n")


@dataclass(frozen=True)
class TokenSpan:
    """A parsed non-overlapping token range."""

    kind: str
    text: str
    start: int
    end: int
    normalized: str | None = None


@dataclass(frozen=True)
class ColorSpan:
    """A best-effort range for text between a color opener and its closing code."""

    opener: TokenSpan
    closer: TokenSpan
    inner_start: int
    inner_end: int


def parse_tokens(value: str) -> list[TokenSpan]:
    """Parse non-overlapping token spans from a localisation value."""
    text = value or ""
    tokens: list[TokenSpan] = []
    index = 0
    length = len(text)

    while index < length:
        if match := _OVER_ESCAPED_NL_RE.match(text, index):
            tokens.append(_span("over_escaped_newline", match))
            index = match.end()
            continue

        if text.startswith(r"\n", index):
            tokens.append(TokenSpan("escaped_newline", r"\n", index, index + 2))
            index += 2
            continue
        if text.startswith(r"\t", index):
            tokens.append(TokenSpan("escaped_tab", r"\t", index, index + 2))
            index += 2
            continue
        if text.startswith(r"\"", index):
            tokens.append(TokenSpan("escaped_quote", r"\"", index, index + 2))
            index += 2
            continue
        if text.startswith(r"\\", index):
            tokens.append(TokenSpan("escaped_bs", r"\\", index, index + 2))
            index += 2
            continue

        char = text[index]
        if char == "[" and (match := _BRACKET_RE.match(text, index)):
            tokens.append(_span("bracket_expr", match))
            index = match.end()
            continue
        if char == "$" and (match := _DOLLAR_RE.match(text, index)):
            tokens.append(_span("dollar_ref", match))
            index = match.end()
            continue
        if char == "£":
            if match := _CLOSED_ICON_RE.match(text, index):
                tokens.append(_span("icon", match))
                index = match.end()
                continue
            if match := _UNCLOSED_ICON_RE.match(text, index):
                name = match.group(1)
                tokens.append(
                    TokenSpan(
                        kind="unclosed_icon",
                        text=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        normalized=f"£{name}£",
                    )
                )
                index = match.end()
                continue
        if char == "§" and (match := _COLOR_RE.match(text, index)):
            tokens.append(_span("color_code", match))
            index = match.end()
            continue

        index += 1

    return tokens


def extract_token_values(value: str) -> dict[str, list[str]]:
    """Return token texts by kind, with malformed icons normalized as icons."""
    result: dict[str, list[str]] = {kind: [] for kind in TOKEN_TYPES}
    for token in parse_tokens(value):
        if token.kind == "unclosed_icon":
            result["icon"].append(token.normalized or token.text)
            result["unclosed_icon"].append(token.text)
            continue
        result[token.kind].append(token.text)
    return result


def close_unclosed_icons(value: str) -> tuple[str, bool]:
    """Close malformed icon tokens while leaving already parsed tokens untouched."""
    tokens = [token for token in parse_tokens(value) if token.kind == "unclosed_icon"]
    if not tokens:
        return value, False

    fixed = value
    for token in reversed(tokens):
        replacement = token.normalized or token.text
        fixed = fixed[: token.start] + replacement + fixed[token.end :]
    return fixed, fixed != value


def iter_color_spans(value: str) -> list[ColorSpan]:
    """Return best-effort color spans using parsed color code token ranges.

    This is intentionally conservative: color openers are any ``§X`` except
    ``§!`` and closers are ``§!``. Literal punctuation between adjacent closers
    remains outside the span, which matches Stellaris patterns like ``§!!§!``.
    """
    stack: list[TokenSpan] = []
    spans: list[ColorSpan] = []
    for token in parse_tokens(value):
        if token.kind != "color_code":
            continue
        if token.text == "§!":
            if not stack:
                continue
            opener = stack.pop()
            spans.append(
                ColorSpan(
                    opener=opener,
                    closer=token,
                    inner_start=opener.end,
                    inner_end=token.start,
                )
            )
        else:
            stack.append(token)
    return spans


def _span(kind: str, match: re.Match[str]) -> TokenSpan:
    return TokenSpan(kind=kind, text=match.group(0), start=match.start(), end=match.end())
