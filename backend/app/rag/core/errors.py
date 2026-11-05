class RagError(Exception):
    """Base class for errors that are safe to show to the model or API caller."""


class UnknownKnowledgeBase(RagError):
    def __init__(self, name: str, known: list[str]):
        self.name, self.known = name, known
        super().__init__(
            f"unknown knowledge base '{name}'. Available: {', '.join(known) or '(none)'}"
        )


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
