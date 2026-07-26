from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "references" / "report-template.md"

REQUIRED_SECTIONS_IN_ORDER = [
    "Executive Summary",
    "Current Configuration",
    "Container Analysis",
    "Replica Impact Summary",
    "Resource Limit Analysis",
    "Estimated Resource Savings",
    "Risk Assessment",
    "Assumptions",
    "Missing Information",
]


def test_all_nine_sections_present_in_order():
    lines = TEMPLATE_PATH.read_text().splitlines()

    line_numbers = []
    for section in REQUIRED_SECTIONS_IN_ORDER:
        heading = f"## {section}"
        matches = [i for i, line in enumerate(lines) if line.strip() == heading]
        assert matches, f"heading {heading!r} not found in report-template.md"
        line_numbers.append(matches[0])

    assert line_numbers == sorted(line_numbers), (
        "section headings are not in the expected order: "
        f"{list(zip(REQUIRED_SECTIONS_IN_ORDER, line_numbers))}"
    )
