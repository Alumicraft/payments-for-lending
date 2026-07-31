"""Regression tests for DCR print-format source files."""

import json
from pathlib import Path


PRINT_FORMATS = Path(__file__).resolve().parents[1] / "dcr" / "print_format"


def test_ach_legal_text_is_constrained_to_the_printable_page():
    source = (
        PRINT_FORMATS
        / "ach_recurring_payment_authorization"
        / "ach_recurring_payment_authorization.json"
    )
    print_format = json.loads(source.read_text())

    assert '<div class="legal-text">' in print_format["html"]
    assert ".inv .legal-text" in print_format["css"]
    assert "width: 92% !important" in print_format["css"]
    assert "white-space: normal !important" in print_format["css"]
    assert "overflow-wrap: break-word !important" in print_format["css"]
