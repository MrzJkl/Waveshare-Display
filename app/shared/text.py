"""Text helpers for panel output.

The bitmap fonts only carry upper case ASCII plus a little punctuation, and
MicroPython's str.upper() is ASCII only, so umlauts and the like have to be
mapped explicitly. plain() does that and drops everything the font cannot
draw; fit() shortens a string until it fits a given pixel width.
"""

TRANSLIT = {
    "ä": "AE", "Ä": "AE", "ö": "OE", "Ö": "OE", "ü": "UE", "Ü": "UE",
    "ß": "SS", "é": "E", "É": "E", "è": "E", "È": "E", "â": "A", "ô": "O",
    "&": "+", "_": " ", "/": "/",
}
DRAWABLE = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,-:/%+"


def plain(text):
    """Upper case, transliterated, reduced to drawable characters.

    Runs of spaces are collapsed and the result is stripped, so joining
    fragments that may be empty stays safe.
    """
    out = ""
    for char in str(text):
        mapped = TRANSLIT.get(char)
        if mapped is None:
            mapped = char.upper()
        for part in mapped:
            if part in DRAWABLE:
                out += part
    while "  " in out:
        out = out.replace("  ", " ")
    return out.strip()


def fit(font, text, max_width, scale=1, bold=False):
    """Drop characters from the end until the text fits max_width pixels."""
    while text and font.text_width(text, scale, bold) > max_width:
        text = text[:-1]
    return text
