"""Operator command line for knowledge bases: create, list, sync.

    python -m app.rag.interfaces.cli create NAME --repo URL [--branch B] [--subdir D] [--description TEXT]
    python -m app.rag.interfaces.cli list
    python -m app.rag.interfaces.cli sync NAME

The CLI is an operator tool: it may point a knowledge base at any local directory, unlike the HTTP API.
It still refuses values that git or the loader would misread as options.
"""

import argparse
import asyncio
import sys

from app.rag.bootstrap import build_rag
from app.rag.core.errors import RagError
from app.rag.interfaces.formatting import format_kbs
from app.rag.interfaces.validation import validate_branch, validate_name, validate_subdir


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kb", description="Manage knowledge bases")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create", help="register a knowledge base")
    c.add_argument("name")
    c.add_argument("--repo", required=True, help="git url, or a local directory")
    c.add_argument("--branch", default="main")
    c.add_argument("--subdir", default="")
    c.add_argument("--description", default="")
    sub.add_parser("list", help="list knowledge bases")
    s = sub.add_parser("sync", help="bring a knowledge base up to date")
    s.add_argument("name")
    return p


async def _run(args: argparse.Namespace) -> int:
    rag = build_rag()
    if args.command == "list":
        print(format_kbs(await rag.catalog.list_kbs()))
        return 0
    if args.command == "create":
        repo = args.repo.strip()
        if not repo or repo.startswith("-"):
            raise ValueError("--repo must be a git url or a directory, not an option")
        name, branch, subdir = validate_name(args.name), validate_branch(args.branch), validate_subdir(args.subdir)
        kb = await rag.store.create_kb(
            name, args.description or name, repo, branch, subdir, rag.embedder.model, rag.embedder.dim
        )
        print(f"created knowledge base '{kb.name}'")
        return 0
    report = await rag.syncer.sync(args.name)
    print(
        f"added={report.added} changed={report.changed} removed={report.removed} "
        f"unchanged={report.unchanged} failed={len(report.failed)}"
    )
    for path, error in report.failed:
        print(f"  failed: {path}: {error}", file=sys.stderr)
    return 1 if report.failed else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (RagError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
