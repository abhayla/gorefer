"""Analytics / event context (05-Database-Design Context 12).

INTENTIONALLY EMPTY in M1. The immutable, append-only `events` log and its
supporting tables land in M4 (analytics/journey). Kept as an app now so the
tenant-scoped boundary and migration graph include it from day one.
"""
