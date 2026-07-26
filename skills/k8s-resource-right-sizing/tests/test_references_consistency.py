from pathlib import Path

METHODOLOGY_PATH = Path(__file__).resolve().parent.parent / "references" / "methodology.md"

REQUIRED_TOKENS = [
    "1.2",
    "1.25",
    "50m",
    "128Mi",
    "256Mi",
    ("2×", "2x"),
    ("1.5×", "1.5x"),
    "0.8",
    "0.9",
    "10%",
    ("7 days", "168"),
    "24",
]


def test_methodology_contains_all_constants():
    text = METHODOLOGY_PATH.read_text()
    for token in REQUIRED_TOKENS:
        if isinstance(token, tuple):
            assert any(alt in text for alt in token), f"none of {token!r} found in methodology.md"
        else:
            assert token in text, f"{token!r} not found in methodology.md"
