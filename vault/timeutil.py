from datetime import timezone


def as_utc(moment):
    """Normalise a database timestamp to aware UTC.

    PostgreSQL returns timestamptz values in the session time zone (e.g. +05:30) and SQLite returns naive
    values that are already UTC. Converting (never relabelling) keeps comparisons and hashes correct.
    """
    if moment is None:
        return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)
