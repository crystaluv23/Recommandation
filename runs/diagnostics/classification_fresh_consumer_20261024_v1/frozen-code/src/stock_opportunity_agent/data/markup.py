"""Source-owned nonvisible HTML ranges with unchanged raw coordinates."""

from __future__ import annotations

from html.parser import HTMLParser
import re

_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_HIDDEN_TAGS = frozenset(("head", "script", "style", "template", "ix:header", "ix:hidden"))
_INLINE_HIDDEN = re.compile(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:!important)?\s*(?:;|$)", re.I)
_TAG = re.compile(r"<[^>]*>", re.DOTALL)


def visible_html_ranges(raw: str) -> tuple[tuple[int, int], ...]:
    """Index visible text in raw coordinates, including reads inside large tags."""

    removed = sorted((*nonvisible_html_ranges(raw), *((m.start(), m.end()) for m in _TAG.finditer(raw))))
    visible = []
    cursor = 0
    for start, end in removed:
        if cursor < start:
            visible.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < len(raw):
        visible.append((cursor, len(raw)))
    return tuple(visible)

def nonvisible_html_ranges(raw: str) -> tuple[tuple[int, int], ...]:
    """Return unchanged raw intervals; malformed open hidden blocks close at EOF."""
    if "<" not in raw:
        return ()

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.line_offsets = [0, *(match.end() for match in re.finditer("\n", raw))]
            self.stack = []
            self.hidden = None
            self.ranges = []

        def raw_offset(self):
            line, column = self.getpos()
            return self.line_offsets[line - 1] + column

        def is_hidden(self, tag, attrs):
            attrs = dict(attrs)
            return (tag in _HIDDEN_TAGS or "hidden" in attrs
                    or bool(_INLINE_HIDDEN.search(attrs.get("style") or "")))

        def handle_starttag(self, tag, attrs):
            if tag in _VOID:
                return
            self.stack.append(tag)
            if self.hidden is None and self.is_hidden(tag, attrs):
                self.hidden = (self.raw_offset(), len(self.stack) - 1)

        def handle_startendtag(self, tag, attrs):
            if self.hidden is None and self.is_hidden(tag, attrs):
                start = self.raw_offset()
                self.ranges.append((start, start + len(self.get_starttag_text())))

        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index] != tag:
                    continue
                if self.hidden is not None and index <= self.hidden[1]:
                    start, _depth = self.hidden
                    end = raw.find(">", self.raw_offset())
                    self.ranges.append((start, len(raw) if end < 0 else end + 1))
                    self.hidden = None
                del self.stack[index:]
                break

    parser = Parser()
    parser.feed(raw)
    parser.close()
    if parser.hidden is not None:
        parser.ranges.append((parser.hidden[0], len(raw)))
    return tuple(parser.ranges)
