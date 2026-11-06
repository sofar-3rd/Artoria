from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://sagent:sagent@localhost:5433/sagent"
    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    # Providers honour `stream_options={"include_usage": true}`; some proxies 400 on it.
    openai_stream_usage: bool = True

    recursion_limit: int = 12
    max_message_chars: int = 4000
    title_max_chars: int = 30
    db_pool_max: int = 5

    # RAG
    rag_enabled: bool = False
    rag_model_dir: str = "./models"
    rag_embed_model: str = "BAAI/bge-m3"
    rag_embed_dim: int = 1024
    rag_embed_batch_size: int = 16
    rag_rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rag_device: str = "cpu"
    rag_recall_candidates: int = 40
    rag_rerank_candidates: int = 20
    rag_top_k: int = 5
    rag_rrf_k: int = 60
    rag_min_rerank_score: float | None = None
    rag_rerank_timeout_s: float = 60.0
    rag_chunk_target_tokens: int = 400
    rag_chunk_max_tokens: int = 512
    rag_chunk_overlap_tokens: int = 50
    rag_min_chunk_chars: int = 60
    rag_clone_dir: str = "./.kb-cache"

    @property
    def sqlalchemy_url(self) -> str:
        # SQLAlchemy needs an explicit driver; psycopg is already a dependency.
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


settings = Settings()
