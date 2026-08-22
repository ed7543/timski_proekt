from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC datetime - a drop-in replacement for the deprecated
    datetime.utcnow(). Deliberately naive (not datetime.now(timezone.utc)
    directly): every DateTime column in this app is naive/UTC-implicit, and
    mixing naive values already in the DB with a newly-aware one raises
    TypeError on comparison (e.g. the token-expiry checks in routes/auth)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
