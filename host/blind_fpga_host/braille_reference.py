"""Restricted English reference model for tests; runs on PC, not FPGA.

No claim of complete UEB conformance. No Chinese, punctuation, contractions,
layout, or physical printing implementation is provided here.
"""

LETTER_DOTS = (
    "1", "12", "14", "145", "15", "124", "1245", "125", "24", "245",
    "13", "123", "134", "1345", "135", "1234", "12345", "1235", "234", "2345",
    "136", "1236", "2456", "1346", "13456", "1356",
)


def dot_mask(dots):
    return sum(1 << (int(dot) - 1) for dot in dots)


CAPITAL = dot_mask("6")
NUMBER = dot_mask("3456")
LETTER = dot_mask("56")


def english_reference(text):
    """Return six-bit cells (bit0=dot1); fail explicitly on unsupported text."""
    cells, numeric = [], False
    for char in text:
        if char == " ":
            cells.append(0)
            numeric = False
        elif "0" <= char <= "9":
            if not numeric:
                cells.append(NUMBER)
            numeric = True
            digit_index = 9 if char == "0" else int(char) - 1
            cells.append(dot_mask(LETTER_DOTS[digit_index]))
        elif "a" <= char <= "z" or "A" <= char <= "Z":
            lower = char.lower()
            if numeric and lower <= "j":
                cells.append(LETTER)
            numeric = False
            if char.isupper():
                cells.append(CAPITAL)
            cells.append(dot_mask(LETTER_DOTS[ord(lower) - ord("a")]))
        else:
            raise ValueError(
                f"Reference model does not support {char!r} (U+{ord(char):04X}); "
                "Chinese and other characters need the planned FPGA translator"
            )
    return cells


def show_cells(cells):
    return "".join(chr(0x2800 + cell) for cell in cells)
