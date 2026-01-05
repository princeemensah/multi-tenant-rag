"""Application configuration using pydantic settings."""
from functools import lru_cache
from typing import List, Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Multi-Tenant RAG System", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")

    database_url: str = Field(env="DATABASE_URL")
    redis_url: str = Field(env="REDIS_URL")

    qdrant_host: str = Field(default="localhost", env="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, env="QDRANT_PORT")
    qdrant_api_key: Optional[str] = Field(default=None, env="QDRANT_API_KEY")

    jwt_secret_key: str = Field(env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=30, env="JWT_EXPIRE_MINUTES")

    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    default_llm_provider: str = Field(default="openai", env="DEFAULT_LLM_PROVIDER")

    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        env="EMBEDDING_MODEL",
    )
    embedding_dimension: int = Field(default=384, env="EMBEDDING_DIMENSION")

    allowed_hosts: Union[List[str], str] = Field(
        default=["localhost", "127.0.0.1", "0.0.0.0"],
        env="ALLOWED_HOSTS",
    )
    max_file_size_mb: int = Field(default=10, env="MAX_FILE_SIZE_MB")
    upload_dir: str = Field(default="./uploads", env="UPLOAD_DIR")
    allowed_file_types: Union[List[str], str] = Field(
        default=["pdf", "txt", "docx"],
        env="ALLOWED_FILE_TYPES",
    )

    chunk_max_chars: int = Field(default=512, env="CHUNK_MAX_CHARS")
    chunk_overlap_chars: int = Field(default=50, env="CHUNK_OVERLAP_CHARS")

    cache_enabled: bool = Field(default=True, env="CACHE_ENABLED")
    cache_namespace: str = Field(default="mt_rag", env="CACHE_NAMESPACE")
    cache_ttl_seconds: int = Field(default=300, env="CACHE_TTL_SECONDS")

    reranker_enabled: bool = Field(default=False, env="RERANKER_ENABLED")
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        env="RERANKER_MODEL",
    )
    reranker_max_candidates: int = Field(default=25, env="RERANKER_MAX_CANDIDATES")

    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="allow",
    )

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, value):
        if isinstance(value, str):
            return [host.strip() for host in value.split(",") if host.strip()]
        return value

    @field_validator("allowed_file_types", mode="before")
    @classmethod
    def parse_allowed_file_types(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
