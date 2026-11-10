"""Shared assertion for the broken-link fallback (owner decision 2026-11-10).

A public link that is not served no longer answers 404: it redirects, inside the site,
towards the default account-opening link. Tests that used to pin "this route does not
exist" with a 404 now pin it with this check - the route still does nothing itself.
"""


def fell_back(resp) -> bool:
    """True when `resp` is the fallback: a 302 to another path on this site."""
    return resp.status_code == 302 and resp.headers.get("Location", "").startswith("/")
