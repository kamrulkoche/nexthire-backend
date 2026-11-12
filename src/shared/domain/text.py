"""Text clean-up for content that arrives from outside.

Job postings come from third parties as HTML of unknown quality. They are
stored as plain text: the frontend renders text, never HTML from a source, so a
posting can never inject markup into the page.
"""

import html
import re
from html.parser import HTMLParser
from typing import Optional

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "tr"}
_SKIP_TAGS = {"script", "style"}
_SPACES = re.compile(r"[ \t\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")


class _TextExtractor(HTMLParser):
    """Collects text, turning block-level tags into line breaks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIP_TAGS:
            self._skipping += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skipping:
            self._skipping -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def strip_html(value: Optional[str]) -> str:
    """Reduce HTML to readable plain text.

    Args:
        value: HTML or plain text, or None

    Returns:
        Plain text with paragraphs kept as blank-line breaks
    """
    if not value:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        # A malformed document still yields its text, just without structure.
        text = re.sub(r"<[^>]+>", " ", html.unescape(value))
    lines = [_SPACES.sub(" ", line).strip() for line in text.splitlines()]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def clip(value: Optional[str], limit: int) -> Optional[str]:
    """Trim and cut a string to a column's length, or None if blank.

    Args:
        value: Any string, or None
        limit: The column's maximum length

    Returns:
        The trimmed value, at most ``limit`` characters, or None
    """
    if value is None:
        return None
    value = " ".join(str(value).split())
    if not value:
        return None
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"
