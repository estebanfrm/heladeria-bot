"""Configuración de la app: todo sale de variables de entorno (.env)."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repo (en la imagen Docker es /app, que replica la misma estructura).
# Así .env y SEED_FILE funcionan igual sin importar desde qué carpeta se ejecute.
RAIZ = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    # Orígenes del frontend que pueden llamar a la API (separados por coma)
    cors_origins: str = "http://localhost:5173"
    # Relativo a la raíz del repo, o absoluto (ej. un archivo secreto montado en producción)
    seed_file: Path = RAIZ / "seeds" / "demo.json"

    # Base de datos
    database_url: str = "postgresql+psycopg://heladeria:heladeria@localhost:5432/heladeria"

    # WhatsApp Cloud API
    wa_phone_number_id: str = ""
    wa_access_token: str = ""
    wa_verify_token: str = ""
    wa_app_secret: str = ""
    wa_menu_pdf_file: Path | None = None  # archivo local; se sube por la API de medios
    wa_api_version: str = "v26.0"  # versión de la Graph API de Meta
    staff_phones: str = ""  # números del personal separados por coma

    # IA
    ia_provider: str = "gemini"
    ia_model: str = ""
    ia_api_key: str = ""
    ia_base_url: str = ""  # opcional: otra URL compatible con OpenAI (ej. Ollama desde Docker)
    ia_timeout: float = 20.0  # segundos
    # Opcional: "none" apaga el razonamiento de modelos que piensan antes de responder
    # (ej. gemma4 en Ollama: de 150 s a 17 s por mensaje). Vacío = lo que use el proveedor.
    ia_reasoning_effort: str = ""

    # Límites
    web_chat_max_msgs_per_session: int = 20
    chat_inactivity_minutes: int = Field(default=30, ge=1, le=1440)
    chat_inactivity_poll_seconds: int = Field(default=60, ge=1, le=3600)
    chat_inactivity_worker_enabled: bool = True

    @field_validator("seed_file")
    @classmethod
    def _seed_relativo_a_la_raiz(cls, ruta: Path) -> Path:
        return ruta if ruta.is_absolute() else RAIZ / ruta

    @field_validator("wa_menu_pdf_file", mode="before")
    @classmethod
    def _pdf_relativo_a_la_raiz(cls, valor: str | Path | None) -> Path | None:
        if not valor:
            return None
        ruta = Path(valor)
        return ruta if ruta.is_absolute() else RAIZ / ruta

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def staff_phone_list(self) -> list[str]:
        return [p.strip() for p in self.staff_phones.split(",") if p.strip()]


settings = Settings()
