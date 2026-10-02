"""Configuración de la app: todo sale de variables de entorno (.env)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env en la raíz del repo, sin importar desde qué carpeta se ejecute (uvicorn, alembic, pytest)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    seed_file: Path = Path("../seeds/demo.json")

    # Base de datos
    database_url: str = "postgresql+psycopg://heladeria:heladeria@localhost:5432/heladeria"

    # WhatsApp Cloud API
    wa_phone_number_id: str = ""
    wa_access_token: str = ""
    wa_verify_token: str = ""
    wa_app_secret: str = ""
    staff_phones: str = ""  # números del personal separados por coma

    # IA
    ia_provider: str = "gemini"
    ia_model: str = ""
    ia_api_key: str = ""

    # Límites
    web_chat_max_msgs_per_session: int = 20

    @property
    def staff_phone_list(self) -> list[str]:
        return [p.strip() for p in self.staff_phones.split(",") if p.strip()]


settings = Settings()
