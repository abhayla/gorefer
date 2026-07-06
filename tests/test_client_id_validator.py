"""client_id format validator (ADR-008 / Gap 3 — format only, no ownership check)."""
import pytest

from apps.referrals.validators import InvalidClientId, validate_client_id


@pytest.mark.parametrize(
    "raw,expected", [("RJ4521", "RJ4521"), ("da1707", "DA1707"), ("  RJ4521  ", "RJ4521")]
)
def test_valid_ids_normalize_uppercase(raw, expected):
    assert validate_client_id(raw) == expected


@pytest.mark.parametrize("bad", ["", "   ", None, "a" * 21, "RJ-4521", "RJ 4521", "RJ/4521", "<script>"])
def test_invalid_ids_rejected(bad):
    with pytest.raises(InvalidClientId):
        validate_client_id(bad)
