"""Dependency rules of app/rag, checked on the real import graph (all imports, lazy ones inside functions too).

The rules are an ALLOW-list per package, not a list of forbidden names: a new dependency that nobody decided
on fails the test instead of slipping through. Design reference: section 7.3 of the design document.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
RAG = BACKEND / "app" / "rag"

# What each sub-package may import from the rest of app.rag. Anything not listed is a violation.
ALLOWED_RAG = {
    "core": set(),
    # The adapters satisfy the core.ports Protocols structurally, so inference/ needs no import of core at all.
    "inference": set(),
    "persistence": {"core"},
    "ingest": {"core", "persistence"},  # sync.py uses Store; chunking/plan/loaders/sources do not (see below)
    "retrieval": {"core", "persistence"},
    "interfaces": {"core", "retrieval", "bootstrap"},  # bootstrap only for the CLI entry point
    "(top)": {"core", "ingest", "inference", "persistence", "retrieval"},  # bootstrap.py is the assembly point
}

# Third-party / application modules a package may use. Everything heavy is here on purpose.
ALLOWED_EXTERNAL = {
    "core": set(),
    "inference": {"torch", "sentence_transformers", "transformers"},
    "persistence": {"sqlalchemy", "pgvector", "app.models"},
    "ingest": {"langchain_text_splitters", "markitdown", "yaml", "app.config"},
    "retrieval": set(),
    "interfaces": {"langchain_core", "pydantic"},
    "(top)": {"app.config", "app.db"},
}
WATCHED_EXTERNAL = {
    "sqlalchemy", "pgvector", "torch", "sentence_transformers", "transformers", "langchain_text_splitters",
    "langchain_core", "langchain", "markitdown", "yaml", "fastapi", "pydantic", "psycopg", "app.models",
    "app.config", "app.db", "app.routers", "app.agent", "app.main",
}

# Finer rules inside a package: file or directory -> app.rag sub-packages it must NOT touch even though the
# package as a whole may.
FILE_FORBIDDEN_RAG = {
    "ingest/chunking.py": {"persistence", "inference", "retrieval", "ingest.sync"},
    "ingest/plan.py": {"persistence", "inference", "retrieval", "ingest.sync"},
    "ingest/frontmatter.py": {"persistence", "inference", "retrieval"},
    "ingest/loaders": {"persistence", "inference", "retrieval"},
    "ingest/sources": {"persistence", "inference", "retrieval"},
    "interfaces/tools.py": {"persistence", "ingest", "inference"},  # the model must not reach sync or SQL
    "interfaces/formatting.py": {"persistence", "ingest", "inference"},
    "retrieval": {"ingest", "inference"},
}
# Files that must not import SQLAlchemy or the ORM even though persistence exists: only store.py talks SQL.
NO_SQL = ["ingest/sync.py", "retrieval", "interfaces/tools.py", "interfaces/formatting.py", "interfaces/cli.py",
          "interfaces/validation.py", "bootstrap.py"]


def all_imports(path: Path) -> set[str]:
    """Every module a file imports, wherever the import statement is (module level, function, class)."""
    mods: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
            mods.update(f"{node.module}.{a.name}" for a in node.names)  # `from app.rag import persistence`
    return mods


def package_of(path: Path) -> str:
    rel = path.relative_to(RAG)
    return rel.parts[0] if len(rel.parts) > 1 else "(top)"


def rag_target(module: str) -> str | None:
    """`app.rag.persistence.store` -> `persistence`; `app.rag.bootstrap` -> `bootstrap`."""
    parts = module.split(".")
    return parts[2] if module.startswith("app.rag.") and len(parts) > 2 else None


def rag_files():
    return sorted(p for p in RAG.rglob("*.py") if "__pycache__" not in p.parts)


def covers(pattern: str, path: Path) -> bool:
    rel = path.relative_to(RAG).as_posix()
    return rel == pattern or rel.startswith(pattern.rstrip("/") + "/")


@pytest.mark.parametrize("path", rag_files(), ids=lambda p: p.relative_to(RAG).as_posix())
def test_package_may_only_import_what_the_architecture_allows(path):
    pkg = package_of(path)
    assert pkg in ALLOWED_RAG, f"{path.relative_to(RAG)} is in a package with no rules: add it to ALLOWED_RAG"
    imports = all_imports(path)
    rag_deps = {t for m in imports if (t := rag_target(m)) and t != pkg}
    # "(top)" files (bootstrap.py, __init__.py) are checked against the (top) row.
    illegal = rag_deps - ALLOWED_RAG[pkg]
    assert not illegal, f"{path.relative_to(RAG)} imports app.rag.{sorted(illegal)}; allowed: {sorted(ALLOWED_RAG[pkg])}"
    external = {w for w in WATCHED_EXTERNAL if any(m == w or m.startswith(w + ".") for m in imports)}
    illegal_ext = external - ALLOWED_EXTERNAL[pkg]
    assert not illegal_ext, f"{path.relative_to(RAG)} imports {sorted(illegal_ext)}; allowed: {sorted(ALLOWED_EXTERNAL[pkg])}"


@pytest.mark.parametrize("path", rag_files(), ids=lambda p: p.relative_to(RAG).as_posix())
def test_finer_rules_inside_a_package(path):
    imports = all_imports(path)
    for pattern, forbidden in FILE_FORBIDDEN_RAG.items():
        if not covers(pattern, path):
            continue
        for module in imports:
            for banned in forbidden:
                prefix = f"app.rag.{banned}"
                assert not (module == prefix or module.startswith(prefix + ".")), (
                    f"{path.relative_to(RAG)} imports {module}, which {pattern} must not depend on"
                )


@pytest.mark.parametrize("path", [p for p in rag_files() if any(covers(x, p) for x in NO_SQL)], ids=lambda p: p.relative_to(RAG).as_posix())
def test_only_the_persistence_package_touches_sql(path):
    imports = all_imports(path)
    bad = {m for m in imports if m.split(".")[0] in ("sqlalchemy", "pgvector") or m.startswith("app.rag.persistence.models")}
    assert not bad, f"{path.relative_to(RAG)} reaches SQL/ORM through {sorted(bad)}; only persistence/ may"


def test_the_model_facing_tools_cannot_reach_sync_or_the_database():
    """The permission boundary: the agent can search and read, never start a sync or write rows."""
    for name in ("tools.py", "formatting.py"):
        imports = all_imports(RAG / "interfaces" / name)
        assert not {m for m in imports if m.startswith(("app.rag.ingest", "app.rag.persistence", "app.db"))}, name


def test_core_is_pure_standard_library():
    """core/ is the vocabulary everything shares: no I/O libraries, no sibling packages."""
    for path in (RAG / "core").glob("*.py"):
        for module in all_imports(path):
            top = module.split(".")[0]
            assert top in sys.stdlib_module_names or module.startswith("app.rag.core"), f"{path.name} imports {module}"


def test_every_subpackage_has_rules():
    packages = {p.name for p in RAG.iterdir() if p.is_dir() and p.name != "__pycache__"}
    assert packages <= set(ALLOWED_RAG), f"packages without rules: {sorted(packages - set(ALLOWED_RAG))}"


def test_the_rules_describe_imports_that_really_exist():
    """A rule nobody exercises rots. Each allowed edge should be used, otherwise delete it."""
    used: dict[str, set[str]] = {p: set() for p in ALLOWED_RAG}
    for path in rag_files():
        pkg = package_of(path)
        for module in all_imports(path):
            if (t := rag_target(module)) and t != pkg:
                used[pkg].add(t)
    unused = {p: sorted(ALLOWED_RAG[p] - used[p]) for p in ALLOWED_RAG if ALLOWED_RAG[p] - used[p]}
    assert not unused, f"allowed but never used (tighten ALLOWED_RAG): {unused}"


@pytest.mark.parametrize(
    "module,heavy",
    [
        ("app.main", ["torch", "sentence_transformers", "transformers"]),
        ("app.rag.bootstrap", ["torch", "sentence_transformers", "transformers"]),
        ("app.rag.interfaces.tools", ["torch", "sentence_transformers", "transformers", "markitdown"]),
        ("app.rag.retrieval.search", ["torch", "sentence_transformers", "transformers", "markitdown"]),
    ],
)
def test_importing_does_not_load_the_heavy_libraries(module, heavy):
    """Start-up and the model-facing code must not pay for torch (seconds) or the pdf stack."""
    code = f"import sys, {module}; bad = [m for m in {heavy!r} if m in sys.modules]; print(bad); sys.exit(1 if bad else 0)"
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, f"importing {module} loaded {done.stdout.strip()} {done.stderr[-300:]}"
