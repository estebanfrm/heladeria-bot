"""Proveedores de IA intercambiables (IA_PROVIDER en .env).

Gemini, Groq, Ollama y OpenAI exponen la API de Chat Completions de OpenAI, así que un solo
cliente HTTP los cubre cambiando la URL base. El resto del código solo conoce `ProveedorIA`.
"""

from typing import Protocol

import httpx

from app.config import Settings


class ErrorIA(RuntimeError):
    """Falla al usar la IA: red, credenciales, límite de uso o respuesta inesperada."""


class ProveedorIA(Protocol):
    def completar_json(self, sistema: str, usuario: str) -> str:
        """Texto (JSON) que genera el modelo para ese prompt."""
        ...


URLS_COMPATIBLES_OPENAI = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://localhost:11434/v1",
    "openai": "https://api.openai.com/v1",
}


class ProveedorCompatibleOpenAI:
    def __init__(
        self,
        base_url: str,
        modelo: str,
        api_key: str = "",
        timeout: float = 20.0,
        reasoning_effort: str = "",
        cliente: httpx.Client | None = None,  # inyectable en tests
    ):
        self.modelo = modelo
        self.reasoning_effort = reasoning_effort
        self._cliente = cliente or httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    def completar_json(self, sistema: str, usuario: str) -> str:
        cuerpo = {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            cuerpo["reasoning_effort"] = self.reasoning_effort
        try:
            respuesta = self._cliente.post("chat/completions", json=cuerpo)
            respuesta.raise_for_status()
            eleccion = respuesta.json()["choices"][0]
            contenido = eleccion["message"]["content"]
        except httpx.HTTPStatusError as e:
            codigo = e.response.status_code
            raise ErrorIA(f"El proveedor de IA respondió {codigo}: {e.response.text[:200]}") from e
        except httpx.HTTPError as e:
            raise ErrorIA(f"No se pudo contactar al proveedor de IA: {e!r}") from e
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise ErrorIA("Respuesta del proveedor de IA con formato inesperado") from e
        if eleccion.get("finish_reason") == "length":
            raise ErrorIA(
                "La respuesta de la IA se cortó por el límite de tokens "
                "(en Ollama: aumentar el contexto del modelo)"
            )
        if not isinstance(contenido, str):
            raise ErrorIA("El proveedor de IA no devolvió texto")
        return contenido


class ProveedorFalso:
    """Devuelve respuestas fijas en orden y guarda los prompts. Para tests, sin red ni API key."""

    def __init__(self, respuestas: list[str]):
        self.respuestas = list(respuestas)
        self.llamadas: list[tuple[str, str]] = []

    def completar_json(self, sistema: str, usuario: str) -> str:
        self.llamadas.append((sistema, usuario))
        if not self.respuestas:
            raise ErrorIA("ProveedorFalso sin respuestas")
        return self.respuestas.pop(0)


class ProveedorNoConfigurado:
    """Reemplazo cuando falta configurar la IA: los botones siguen funcionando y cada texto
    falla con el motivo (el motor lo cuenta como "no entendí" y lo deja en el log)."""

    def __init__(self, motivo: str):
        self.motivo = motivo

    def completar_json(self, sistema: str, usuario: str) -> str:
        raise ErrorIA(f"IA no configurada: {self.motivo}")


def crear_proveedor(config: Settings) -> ProveedorIA:
    """Proveedor según .env (IA_PROVIDER, IA_MODEL, IA_API_KEY, IA_BASE_URL, IA_TIMEOUT)."""
    nombre = config.ia_provider.strip().lower()
    base_url = config.ia_base_url or URLS_COMPATIBLES_OPENAI.get(nombre)
    if base_url is None:
        opciones = " | ".join(URLS_COMPATIBLES_OPENAI)
        raise ValueError(
            f"IA_PROVIDER='{config.ia_provider}' aún no está soportado. Usa {opciones}, "
            "o define IA_BASE_URL con otra API compatible con OpenAI."
        )
    if not config.ia_model:
        raise ValueError("Falta IA_MODEL en .env (el modelo vigente en la consola del proveedor).")
    if not config.ia_api_key and nombre != "ollama" and not config.ia_base_url:
        raise ValueError(f"Falta IA_API_KEY en .env para '{nombre}'.")
    return ProveedorCompatibleOpenAI(
        base_url,
        config.ia_model,
        config.ia_api_key,
        config.ia_timeout,
        reasoning_effort=config.ia_reasoning_effort,
    )
