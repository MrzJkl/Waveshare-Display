"""Small 5x7 trend symbols for the water level widget.

There is deliberately no "steady" symbol: a horizontal dash next to the value
reads as a minus sign. A steady level simply draws no arrow.
"""

from app.shared.font import Font

TREND = Font({
    "up": (
        "..1..",
        ".111.",
        "11111",
        "..1..",
        "..1..",
        "..1..",
        "..1..",
    ),
    "down": (
        "..1..",
        "..1..",
        "..1..",
        "..1..",
        "11111",
        ".111.",
        "..1..",
    ),
    " ": (
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
    ),
}, 7, fallback=" ")

WIDTH = 5
