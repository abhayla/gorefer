"""Phone normalization — the single canonical helper (implementation/10 §3)."""
import pytest

from apps.common.phone import normalize_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("9876543210", "919876543210"),
        ("+91 98765 43210", "919876543210"),
        ("(98765)-43210", "919876543210"),
        ("91 98765 43210", "919876543210"),
        ("+919876543210", "919876543210"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected
