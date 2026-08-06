# ============================================================
# WhatsApp CRM - Backend configuration
# Loads values from environment variables (.env) via pydantic-settings
# ============================================================
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "WhatsApp CRM"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api"

    # --- Database (Supabase Postgres) ---
    # Example (Supabase):
    # postgresql+asyncpg://postgres:[password]@db.[ref].supabase.co:5432/postgres?sslmode=require
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/whatsapp_crm"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Security ---
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    token_type: str = "bearer"

    # --- CORS ---
    # Comma separated list of allowed origins
    cors_origins: str = (
        "http://localhost:5500,http://127.0.0.1:5500,"
        "http://localhost:5173,http://localhost:3000,"
        "https://your-frontend.vercel.app"
    )

    # --- Supabase Storage ---
    supabase_url: str = "https://your-project.supabase.co"
    supabase_service_key: str = "your-service-role-key"
    supabase_bucket: str = "whatsapp-media"

    # --- Meta WhatsApp Cloud API ---
    whatsapp_api_version: str = "v21.0"
    whatsapp_graph_url: str = "https://graph.facebook.com"
    whatsapp_default_access_token: str = ""
    whatsapp_default_phone_number_id: str = ""
    webhook_default_verify_token: str = "change-me-verify-token"

    # --- WebSocket ---
    ws_heartbeat_seconds: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_uri(self) -> str:
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
