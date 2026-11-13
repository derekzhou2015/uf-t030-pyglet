"""Line fitting must use the same pixel-rounded advances as the renderer.

Font metrics and shaping offsets are fractional, but glyphs are positioned with
per-glyph pixel rounding.  The layout therefore has to accumulate rounded advances
when deciding where to wrap.  Comparing a raw fractional sum against the integer
layout width wraps a line whose rendered width is exactly the layout width, while a
genuinely overflowing line can round down and slip through.
"""

import pytest

from pyglet.font.base import GlyphPosition
from pyglet.text import runlist
from pyglet.text.document import FormattedDocument
from pyglet.text.layout import TextLayout

# A fractional advance keeps the raw accumulation and the rendered (rounded) width
# apart: 10.4 renders as 10 pixels per glyph.
FRACTIONAL_ADVANCE = 10.4


@pytest.fixture(autouse=True)
def dummy_layout_shaders(monkeypatch, get_dummy_shader_program):
    """Avoid creating a GL context just to lay out text."""
    monkeypatch.setattr("pyglet.text.layout.base.get_default_layout_shader", get_dummy_shader_program)
    monkeypatch.setattr("pyglet.text.layout.base.get_default_decoration_shader", get_dummy_shader_program)


class _FakeGlyph:
    def __init__(self, advance):
        self.advance = advance


class _FakeFont:
    ascent = 10
    descent = -2


class _FixedAdvanceDocument(FormattedDocument):
    """Document whose font gives every glyph the same fractional advance."""

    def __init__(self, text, advance=FRACTIONAL_ADVANCE):
        super().__init__(text)
        self.advance = advance
        self._font = _FakeFont()

    def get_font_runs(self, dpi=None):
        return runlist.ConstRunIterator(len(self.text), self._font)

    def get_font(self, position=0, dpi=None):
        return self._font


def _flow(text, width, wrap=None):
    """Flow ``text`` into lines of ``width`` and return the resulting lines.

    Lines are split by their start offsets, which is unambiguous for both wrap modes.
    """
    document = _FixedAdvanceDocument(text)
    if wrap is not None:
        document.set_style(0, len(text), {"wrap": wrap})

    layout = TextLayout(document, width=width, height=100, multiline=True, wrap_lines=True,
                        init_document=False)

    glyphs = [_FakeGlyph(FRACTIONAL_ADVANCE) for _ in text]
    offsets = [GlyphPosition(0, 0, 0, 0) for _ in text]
    owner_runs = runlist.RunList(len(text), object())
    return list(layout._flow_glyphs_wrap(glyphs, offsets, owner_runs, 0, len(text)))


def _line_texts(text, lines):
    result = []
    for i, line in enumerate(lines):
        end = lines[i + 1].start if i + 1 < len(lines) else len(text)
        result.append(text[line.start:end])
    return result


class TestWordWrapBoundary:
    text = "ab cd"

    def test_line_exactly_at_width_does_not_wrap(self):
        # "ab cd" renders as exactly 5 * 10 = 50 pixels, so it must fit on one line.
        lines = _flow(self.text, width=50)
        assert _line_texts(self.text, lines) == ["ab cd"]
        assert [line.width for line in lines] == [50]

    def test_line_over_width_still_wraps(self):
        # One pixel narrower than the rendered width: it must wrap.
        lines = _flow(self.text, width=49)
        assert _line_texts(self.text, lines) == ["ab ", "cd"]
        assert [line.width for line in lines] == [30, 20]

    def test_multi_line_continuity(self):
        text = "ab cd ef"
        lines = _flow(text, width=50)
        # The first line breaks before "ef"; the trailing space is kept in the
        # document slice but excluded from the reported line width.
        assert _line_texts(text, lines) == ["ab cd ", "ef"]
        assert [line.width for line in lines] == [50, 20]
        assert all(line.width <= 50 for line in lines)


class TestCharWrapBoundary:
    text = "abcdef"

    def test_line_exactly_at_width_does_not_wrap(self):
        # Three characters render as exactly 3 * 10 = 30 pixels.
        lines = _flow(self.text, width=30, wrap="char")
        assert _line_texts(self.text, lines) == ["abc", "def"]
        assert [line.width for line in lines] == [30, 30]

    def test_line_over_width_still_wraps(self):
        lines = _flow(self.text, width=29, wrap="char")
        assert _line_texts(self.text, lines) == ["ab", "cd", "ef"]
        assert [line.width for line in lines] == [20, 20, 20]

    def test_multi_line_continuity(self):
        text = "abcdefghij"
        lines = _flow(text, width=30, wrap="char")
        assert _line_texts(text, lines) == ["abc", "def", "ghi", "j"]
        assert [line.width for line in lines] == [30, 30, 30, 10]
        assert all(line.width <= 30 for line in lines)
