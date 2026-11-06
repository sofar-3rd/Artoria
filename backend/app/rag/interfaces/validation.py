"""Validation of knowledge base definitions that arrive over HTTP.

The HTTP API is reachable by whoever can reach the server, so what it may point a knowledge base at is
restricted: remote git repositories, and local directories only inside an operator-chosen root. The CLI
is an operator tool and is not subject to the local-path restriction.
"""

import re
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]{1,64}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,99}$")
_REMOTE_RE = re.compile(r"^(https://|ssh://|git://)[^\s]+$|^[A-Za-z0-9._\-]+@[A-Za-z0-9.\-]+:[^\s]+$")


def validate_name(name: str) -> str:
    if not NAME_RE.match(name):
        raise ValueError("name must be 1-64 characters: letters, digits, '_', '-' or CJK characters")
    return name


def validate_branch(branch: str) -> str:
    if not BRANCH_RE.match(branch) or ".." in branch:
        raise ValueError("branch contains characters that are not allowed")
    return branch


def validate_repo_url(repo_url: str, *, local_root: str = "") -> str:
    """Return the location to store. Remote urls pass as they are; local paths must stay inside `local_root`."""
    value = repo_url.strip()
    if not value or value.startswith("-"):
        raise ValueError("repo_url must be a remote git url or an allowed local directory")
    if _REMOTE_RE.match(value):
        return value
    path = value.removeprefix("dir:").strip()
    if not path:
        raise ValueError("repo_url must not be empty")
    if not local_root:
        raise ValueError("local directories are not allowed through the API; use a remote git url")
    root = Path(local_root).resolve()
    target = Path(path).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"local directory must be inside {root}")
    return f"dir:{target}"


def validate_subdir(subdir: str) -> str:
    """A subdirectory is always relative to the source root; reject anything that tries to leave it."""
    clean = subdir.strip().strip("/")
    if not clean:
        return ""
    if ".." in Path(clean).parts or "\x00" in clean or "\n" in clean or "\r" in clean:
        raise ValueError("subdir must be a relative path without '..'")
    return clean
