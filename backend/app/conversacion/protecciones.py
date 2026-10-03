"""Respuestas comerciales seguras y normalización de comandos; precios siempre desde BD."""

import re
import unicodedata


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).lower()
    return " ".join(
        "".join(
            c for c in texto if not unicodedata.combining(c) and unicodedata.category(c) != "Cf"
        ).split()
    )


CONDICIONES_NO_AUTORIZADAS = re.compile(
    r"\b(?:descuento\w*|deskuento\w*|descuent\w*|dscuent\w*|rebaja\w*|cupon\w*|"
    r"promocion\w*|promo|gratis|gratuit\w*|cortesia|regala\w*)\b|\b[23]\s*[x×]\s*[12]\b|"
    r"(?:precio|total)\s*[:=]\s*[-\d$]|(?:cobra\w*|dejalo|dejame)\s+(?:a|en|por)\s*\$?\d",
)
INSTRUCCIONES_AJENAS = re.compile(
    r"(?:ignora|olvida|ignorar)\s+(?:todas?\s+)?(?:las?\s+)?(?:instrucciones|reglas)|"
    r"\b(?:soy|eres)\s+(?:el\s+)?(?:administrador|admin|dueno|system|developer)\b|"
    r"\b(?:marca|pon|cambia)\b.{0,50}\b(?:pagado|pago_verificado|precio|despachado)\b|"
    r"\bdrop\s+table\b|[\"']role[\"']\s*:\s*[\"'](?:system|developer)",
)
CAMBIO = re.compile(r"\b(?:cambi\w*|modific\w*|corrig\w*|quitar|quita|agreg\w*|anad\w*)\b")
CANTIDAD_INVALIDA = re.compile(
    r"(?<![\w#])(?:-\s*\d+|\d+[.,]\d+|0|cero|medio|media)\s+"
    r"(?:graniz\w*|granis\w*|cop\w*|malt\w*|helad\w*|banana\w*|waff\w*|"
    r"ensalad\w*|prod\w*|unidades?)\b"
)


def restriccion_comercial(texto: str) -> bool:
    normal = normalizar(texto)
    return bool(CONDICIONES_NO_AUTORIZADAS.search(normal) or INSTRUCCIONES_AJENAS.search(normal))


def cantidad_invalida(texto: str) -> bool:
    """No permitir que la IA convierta una cantidad explícita inválida en una unidad."""
    return bool(CANTIDAD_INVALIDA.search(normalizar(texto)))
