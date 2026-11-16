"""Application settings — all config via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "netsync-cloud"
    debug: bool = False

    # Supabase
    supabase_url: str = ""                      # https://<project>.supabase.co
    supabase_service_role_key: str = ""         # server-side only, never in agent
    supabase_jwt_secret: str = ""               # legacy HS256 projects

    # JWT verification: "auto" tries JWKS first when no secret is set
    jwt_audience: str = "authenticated"
    jwt_algorithms: list[str] = ["HS256", "ES256"]

    # Device registry backend: "memory" (dev/test) or "supabase" (prod)
    device_store: str = "memory"

    # AI (Phase 5)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-lite"


settings = Settings()
