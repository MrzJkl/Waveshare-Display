"""Bitmap font rendering on framebuf.FrameBuffer targets.

Glyphs are 5x7 bit patterns. Each (character, scale) is rendered once into a
MONO_HLSB FrameBuffer and then blitted at C speed with a two-entry palette:
source 0 -> background (or transparent), source 1 -> text colour.
"""

import framebuf

GLYPHS_5X7 = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "10000", "10000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ":": ("00000", "00100", "00100", "00000", "00100", "00100", "00000"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
}


class Font5x7:
    WIDTH = 5
    HEIGHT = 7
    SPACING = 1

    def __init__(self):
        self._glyphs = {}     # (char, scale) -> FrameBuffer (MONO_HLSB)
        self._palettes = {}   # (colour, background) -> FrameBuffer (GS8, 2x1)

    def text_width(self, text, scale=1):
        n = len(text)
        if n == 0:
            return 0
        return (n * self.WIDTH + (n - 1) * self.SPACING) * scale

    def text_height(self, scale=1):
        return self.HEIGHT * scale

    def _glyph(self, ch, scale):
        key = (ch, scale)
        glyph = self._glyphs.get(key)
        if glyph is None:
            rows = GLYPHS_5X7.get(ch) or GLYPHS_5X7[" "]
            w = self.WIDTH * scale
            h = self.HEIGHT * scale
            glyph = framebuf.FrameBuffer(bytearray(((w + 7) // 8) * h), w, h, framebuf.MONO_HLSB)
            for gy, bits in enumerate(rows):
                for gx, bit in enumerate(bits):
                    if bit == "1":
                        glyph.fill_rect(gx * scale, gy * scale, scale, scale, 1)
            self._glyphs[key] = glyph
        return glyph

    def _palette(self, colour, background):
        key = (colour, background)
        palette = self._palettes.get(key)
        if palette is None:
            palette = framebuf.FrameBuffer(bytearray((background, colour)), 2, 1, framebuf.GS8)
            self._palettes[key] = palette
        return palette

    def draw(self, fb, text, x, y, colour, scale=1, background=None):
        """Draw `text` with its top-left corner at (x, y); returns the x after the text.

        background=None leaves the pixels around the glyph strokes untouched
        (blit skips source 0, which the palette maps to 0; black text on a
        transparent background is therefore not possible).
        """
        if background is None:
            palette = self._palette(colour, 0)
            key = 0
        else:
            palette = self._palette(colour, background)
            key = -1
        advance = (self.WIDTH + self.SPACING) * scale
        for ch in text:
            fb.blit(self._glyph(ch, scale), x, y, key, palette)
            x += advance
        return x
