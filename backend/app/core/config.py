from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from the environment (12-factor). See .env.example."""

    # Works from the repo root or from backend/ (Makefile targets cd into backend).
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8",
                                      extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # security
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 720
    cookie_name: str = "cl_session"
    cookie_secure: bool = False
    # NoDecode: accept "a,b" from env instead of requiring a JSON array.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    login_code_ttl_seconds: int = 600
    login_code_max_attempts: int = 5

    # stores
    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 10
    redis_url: str = "redis://localhost:6379/0"

    # object storage
    s3_endpoint_url: str | None = None
    s3_public_endpoint_url: str | None = None
    s3_bucket: str = "campus-lost-photos"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    upload_max_bytes: int = 8 * 1024 * 1024
    upload_url_ttl_seconds: int = 300

    # email
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "Campus Lost & Found <no-reply@campus.ca>"
    dev_log_login_codes: bool = False

    # llm
    llm_provider: Literal["none", "openai_compat"] = "none"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 12.0

    # embeddings
    embedding_provider: Literal["hashing", "sentence_transformers"] = "hashing"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # matching / lifecycle
    match_notify_threshold: float = 0.70
    match_suggest_threshold: float = 0.45
    match_candidate_pool: int = 50  # ANN top-K before precise scoring
    item_retention_days: int = 60
    lost_report_ttl_days: int = 60
    max_claim_attempts_per_item: int = 3

    # rate limits (requests per window)
    rl_assistant_per_minute: int = 12
    rl_reports_per_hour: int = 20
    rl_claims_per_hour: int = 10
    rl_login_per_hour: int = 8

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str) and not v.startswith("["):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @model_validator(mode="after")
    def _no_dev_defaults_in_production(self) -> "Settings":
        if self.environment == "production":
            weak = [name for name, value in (("JWT_SECRET", self.jwt_secret),
                                             ("S3_SECRET_KEY", self.s3_secret_key))
                    if "change-me" in value or value.startswith("dev-")]
            if weak:
                raise ValueError(f"Refusing to start in production with dev defaults: {weak}")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
