"""Removing credentials from text that may be logged or served by an unauthenticated endpoint."""

import re

# `https://user:token@host/...` and `https://token@host/...` both have a userinfo part; one pattern covers both.
_USERINFO = re.compile(r"(?P<scheme>\b(?:https?|ssh|git|ftp)://)[^/\s@]+@")


def redact_url(text: str) -> str:
    """Replace the userinfo part of every url in `text` with `***`, keeping the scheme and the host."""
    return _USERINFO.sub(lambda m: f"{m.group('scheme')}***@", text)
