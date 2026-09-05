"""Warning triangles for the DWD warning level widget, 12 x 12.

"solid" marks an active warning, "outline" an advance notice
(Vorabinformation). "excl" is the exclamation mark drawn on top: in black on
the solid triangle, in the level colour on the outlined one.
"""

from app.shared.font import Font

ICONS = Font({
    "solid": (
        ".....11.....",
        ".....11.....",
        "....1111....",
        "....1111....",
        "...111111...",
        "...111111...",
        "..11111111..",
        "..11111111..",
        ".1111111111.",
        ".1111111111.",
        "111111111111",
        "111111111111",
    ),
    "outline": (
        ".....11.....",
        ".....11.....",
        "....1..1....",
        "....1..1....",
        "...1....1...",
        "...1....1...",
        "..1......1..",
        "..1......1..",
        ".1........1.",
        ".1........1.",
        "111111111111",
        "111111111111",
    ),
    "excl": (
        "............",
        "............",
        "............",
        "............",
        ".....11.....",
        ".....11.....",
        ".....11.....",
        ".....11.....",
        "............",
        ".....11.....",
        "............",
        "............",
    ),
}, 12, fallback="excl")

WIDTH = 12
HEIGHT = 12
