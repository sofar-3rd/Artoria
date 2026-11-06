from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from app.rag.core.errors import RagError
from app.rag.interfaces.formatting import format_error, format_hits, format_kbs, format_page
from app.rag.retrieval.catalog import Catalog
from app.rag.retrieval.search import Searcher

MAX_TOP_K = 10


class _NoArgs(BaseModel):
    pass


def _search_args(default_top_k: int) -> type[BaseModel]:
    """The search schema is built per call so `top_k` advertises (and receives) the configured default."""

    class SearchArgs(BaseModel):
        query: str = Field(description="What to look for. Be specific; use the terms a document would use.")
        kbs: list[str] = Field(
            min_length=1,
            description="Names of the knowledge bases to search, taken from list_knowledge_bases.",
        )
        top_k: int = Field(
            default=default_top_k, description=f"How many passages to return (1 to {MAX_TOP_K})."
        )

    return SearchArgs


class _ReadArgs(BaseModel):
    doc_id: str = Field(description="The doc_id shown in a search result.")
    offset: int = Field(default=0, description="Character offset to start reading from.")
    limit: int = Field(default=6000, description="Maximum number of characters to return.")


def _explain_bad_arguments(exc) -> str:
    """Turn a pydantic validation error into a short instruction the model can act on."""
    problems = "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in exc.errors()
    )
    return f"error: invalid arguments ({problems}). Fix the arguments and call the tool again."


def build_kb_tools(catalog: Catalog, searcher: Searcher, default_top_k: int = 5) -> list[BaseTool]:
    async def list_knowledge_bases() -> str:
        try:
            return format_kbs(await catalog.list_kbs())
        except RagError as exc:
            return format_error(exc)

    async def search_knowledge_base(query: str, kbs: list[str], top_k: int) -> str:
        try:
            result = await searcher.search(query, kbs, min(max(top_k, 1), MAX_TOP_K))
            return format_hits(result, kbs)
        except (RagError, ValueError) as exc:
            return format_error(exc)

    async def read_document(doc_id: str, offset: int = 0, limit: int = 6000) -> str:
        try:
            return format_page(await catalog.read_document(doc_id, offset, limit))
        except (RagError, ValueError) as exc:
            return format_error(exc)

    return [
        StructuredTool.from_function(
            coroutine=list_knowledge_bases,
            name="list_knowledge_bases",
            description=(
                "List the available knowledge bases with a description of what each one contains. "
                "Call this first to decide which knowledge base to search."
            ),
            args_schema=_NoArgs,
        ),
        StructuredTool.from_function(
            coroutine=search_knowledge_base,
            name="search_knowledge_base",
            description=(
                "Search one or more knowledge bases and return the most relevant passages, each with its "
                "source document. Choose `kbs` from list_knowledge_bases. Prefer several small, specific "
                "searches over one broad search. If a passage is cut off or lacks context, call "
                "read_document with its doc_id and an offset near the passage's start. Cite the document "
                "path in your answer, and say so if nothing relevant is found."
            ),
            args_schema=_search_args(default_top_k),
            handle_validation_error=_explain_bad_arguments,
        ),
        StructuredTool.from_function(
            coroutine=read_document,
            name="read_document",
            description=(
                "Read a document (or a part of it) by doc_id, as returned by search_knowledge_base. "
                "Long documents are paged: when the result says has_more, call again with the next offset."
            ),
            args_schema=_ReadArgs,
            handle_validation_error=_explain_bad_arguments,
        ),
    ]
