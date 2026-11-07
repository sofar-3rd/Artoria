class RagError(Exception):
    """Base class for errors that are safe to show to the model or API caller."""


class UnknownKnowledgeBase(RagError):
    def __init__(self, name: str, known: list[str]):
        self.name, self.known = name, known
        super().__init__(
            f"unknown knowledge base '{name}'. Available: {', '.join(known) or '(none)'}"
        )


class KnowledgeBaseExists(RagError):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"knowledge base '{name}' already exists")


class DocumentNotFound(RagError):
    def __init__(self, doc_id: str):
        super().__init__(f"document '{doc_id}' not found")


class SyncInProgress(RagError):
    def __init__(self, kb: str):
        super().__init__(f"a sync of knowledge base '{kb}' is already running")


class EmbeddingModelMismatch(RagError):
    def __init__(self, kb: str, expected: str, actual: str):
        super().__init__(
            f"knowledge base '{kb}' was indexed with '{expected}' but '{actual}' is "
            "configured; rebuild the index"
        )


class EmptyDocument(RagError):
    def __init__(self, path: str):
        super().__init__(f"no extractable text in '{path}' (scanned PDF?)")


class SourceUnavailable(RagError):
    """The document source cannot be read (missing directory, bad subdir) or looks wrongly empty.

    The message is redacted here rather than at each raise site: a source error can quote a repository URL,
    and these messages are stored in `last_error`, which an unauthenticated endpoint returns.
    """

    def __init__(self, message: str):
        from app.rag.core.redact import redact_url

        super().__init__(redact_url(message))
