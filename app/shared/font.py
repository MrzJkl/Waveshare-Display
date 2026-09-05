"""Bitmap fonts rendered on framebuf.FrameBuffer targets.

Glyphs are tuples of row strings ("1" = pixel on); the glyph width is the
length of a row, so a font may mix widths (narrow colon, wide letters). Each
(character, scale) is rendered once into a MONO_HLSB FrameBuffer and then
blitted at C speed with a two-entry palette: source 0 -> background (or
transparent), source 1 -> text colour.

A colour may also be a pair (a, b): the text is drawn in a with every second
pixel (checkerboard) in b. On the panel the two blend into a mixed colour,
e.g. (RED, YELLOW) reads as orange from a normal viewing distance, and with
b = 0 (black) only half of the pixels light up, which reads as a darker shade,
e.g. (GREEN, 0) for dark green or (WHITE, 0) for grey.
bold=True thickens every stroke by one pixel to the right.

FONT_5X7      letters, digits and punctuation for general text
FONT_DIGITAL  3x7 seven-segment style digits for large clock displays
"""

import framebuf

GLYPHS_5X7 = {
    " ": ("00", "00", "00", "00", "00", "00", "00"),
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
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "10001", "11001", "10101", "10011", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "10001", "01010", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    ".": ("0", "0", "0", "0", "0", "0", "1"),
    ":": ("0", "1", "1", "0", "1", "1", "0"),
    ",": ("00", "00", "00", "00", "00", "01", "10"),
    "-": ("000", "000", "000", "111", "000", "000", "000"),
    "+": ("000", "010", "010", "111", "010", "010", "000"),
    "/": ("00001", "00001", "00010", "00100", "01000", "10000", "10000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "°": ("010", "101", "010", "000", "000", "000", "000"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    "!": ("1", "1", "1", "1", "1", "0", "1"),
}

# Seven-segment style digits, 3 wide, for large time displays.
GLYPHS_DIGITAL_3X7 = {
    " ": ("00", "00", "00", "00", "00", "00", "00"),
    "0": ("111", "101", "101", "101", "101", "101", "111"),
    "1": ("001", "001", "001", "001", "001", "001", "001"),
    "2": ("111", "001", "001", "111", "100", "100", "111"),
    "3": ("111", "001", "001", "111", "001", "001", "111"),
    "4": ("101", "101", "101", "111", "001", "001", "001"),
    "5": ("111", "100", "100", "111", "001", "001", "111"),
    "6": ("111", "100", "100", "111", "101", "101", "111"),
    "7": ("111", "001", "001", "001", "001", "001", "001"),
    "8": ("111", "101", "101", "111", "101", "101", "111"),
    "9": ("111", "101", "101", "111", "001", "001", "111"),
    ":": ("0", "0", "1", "0", "1", "0", "0"),
    ".": ("0", "0", "0", "0", "0", "0", "1"),
    "-": ("000", "000", "000", "111", "000", "000", "000"),
}


class Font:
    def __init__(self, glyphs, height, spacing=1, fallback=" "):
        self.glyphs = glyphs
        self.height = height
        self.spacing = spacing
        self.fallback = glyphs[fallback]
        self._cache = {}      # (char, scale, dither, bold) -> FrameBuffer (MONO_HLSB)
        self._palettes = {}   # (colour, background) -> FrameBuffer (GS8, 2x1)

    def glyph_width(self, ch, scale=1, bold=False):
        return len(self.glyphs.get(ch, self.fallback)[0]) * scale + (1 if bold else 0)

    def text_width(self, text, scale=1, bold=False):
        if not text:
            return 0
        width = 0
        for ch in text:
            width += self.glyph_width(ch, scale, bold)
        return width + (len(text) - 1) * self.spacing * scale

    def text_height(self, scale=1):
        return self.height * scale

    def _glyph(self, ch, scale, dither=False, bold=False):
        key = (ch, scale, dither, bold)
        glyph = self._cache.get(key)
        if glyph is None:
            rows = self.glyphs.get(ch, self.fallback)
            extra = 1 if bold else 0
            w = len(rows[0]) * scale + extra
            h = self.height * scale
            glyph = framebuf.FrameBuffer(bytearray(((w + 7) // 8) * h), w, h, framebuf.MONO_HLSB)
            for gy, bits in enumerate(rows):
                for gx, bit in enumerate(bits):
                    if bit == "1":
                        glyph.fill_rect(gx * scale, gy * scale, scale + extra, scale, 1)
            if dither:
                # keep only the checkerboard half of the stroke pixels
                for py in range(h):
                    for px in range((py + 1) % 2, w, 2):
                        glyph.pixel(px, py, 0)
            self._cache[key] = glyph
        return glyph

    def _palette(self, colour, background):
        key = (colour, background)
        palette = self._palettes.get(key)
        if palette is None:
            palette = framebuf.FrameBuffer(bytearray((background, colour)), 2, 1, framebuf.GS8)
            self._palettes[key] = palette
        return palette

    def draw_glyph(self, fb, key, x, y, colour, scale=1):
        """Draw one glyph by dictionary key with transparent background
        (keys may be whole words, e.g. icon names)."""
        self._blit(fb, key, x, y, colour, None, scale, False)
        return x + self.glyph_width(key, scale)

    def _blit(self, fb, ch, x, y, colour, background, scale, bold):
        second = None
        if isinstance(colour, tuple):
            colour, second = colour
            if second == 0:
                # darker shade: only the checkerboard half of the strokes
                fb.blit(self._glyph(ch, scale, True, bold), x, y, 0, self._palette(colour, 0))
                return
        if background is None:
            fb.blit(self._glyph(ch, scale, False, bold), x, y, 0, self._palette(colour, 0))
        else:
            fb.blit(self._glyph(ch, scale, False, bold), x, y, -1, self._palette(colour, background))
        if second is not None:
            fb.blit(self._glyph(ch, scale, True, bold), x, y, 0, self._palette(second, 0))

    def draw(self, fb, text, x, y, colour, scale=1, background=None, bold=False):
        """Draw `text` with its top-left corner at (x, y); returns the x after the text.

        colour may be a (a, b) pair for a dithered mixed colour; bold thickens
        the strokes by one pixel.
        background=None leaves the pixels around the glyph strokes untouched
        (blit skips source 0, which the palette maps to 0; black text on a
        transparent background is therefore not possible).
        """
        spacing = self.spacing * scale
        for ch in text:
            self._blit(fb, ch, x, y, colour, background, scale, bold)
            x += self.glyph_width(ch, scale, bold) + spacing
        return x


FONT_5X7 = Font(GLYPHS_5X7, 7)
FONT_DIGITAL = Font(GLYPHS_DIGITAL_3X7, 7)
