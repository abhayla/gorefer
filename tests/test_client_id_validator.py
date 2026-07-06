"""client_id format validator (ADR-008 / Gap 3 — format only, no ownership check)."""
import pytest

from apps.referrals.validators import InvalidClientId, validate_client_id


@pytest.mark.parametrize(
    "raw,expected", [("RJ4521", "RJ4521"), ("da1707", "DA1707"), ("  RJ4521  ", "RJ4521")]
)
def test_valid_ids_normalize_uppercase(raw, expected):
    assert validate_client_id(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "", "   ", None,
        "RJ-4521", "RJ 4521", "RJ/4521", "<script>",
        "abc",          # 3 chars — below the spec's 4-char minimum (A-min)
        "a" * 17,       # 17 chars — above the spec's 16-char maximum (A-min)
        "a" * 21,       # oversized
    ],
)
def test_invalid_ids_rejected(bad):
    with pytest.raises(InvalidClientId):
        validate_client_id(bad)


@pytest.mark.parametrize("ok", ["RJ45", "a" * 16, "DA1707"])
def test_boundary_lengths_accepted(ok):
    # 4 and 16 chars are the inclusive bounds (06-API §4.1).
    assert validate_client_id(ok) == ok.upper()
