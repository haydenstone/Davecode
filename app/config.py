"""AENIMUS configuration v0.1.0."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AENIMUS_", env_file=".env", extra="ignore"
    )
    host: str = "127.0.0.1"
    port: int = 8787
    workspace: Path = Path("workspace")
    data_dir: Path = Path("data")
    ollama_url: str = "http://127.0.0.1:11434"
    require_approval: bool = True
    max_file_bytes: int = 1_048_576
    command_timeout: int = 30
    qdrant_url: str = "http://127.0.0.1:6333"
    embedding_model: str = "nomic-embed-text"
    providers_json: str = "{}"
    discord_enabled: bool = False
    # Keep disabled connector IDs as strings so an empty environment value is valid.
    discord_channel_id: str = ""
    discord_allowed_user_ids: str = ""
    discord_command_prefix: str = "!aenimus"


settings = Settings()
