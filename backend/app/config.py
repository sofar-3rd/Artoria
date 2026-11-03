from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://sagent:sagent@localhost:5433/sagent"
    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"

    recursion_limit: int = 12
    max_message_chars: int = 4000
    title_max_chars: int = 30
    db_pool_max: int = 5

    @property
    def sqlalchemy_url(self) -> str:
        # SQLAlchemy needs an explicit driver; psycopg is already a dependency.
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


settings = Settings()
