"""Evalúa el proveedor de IA configurado en .env con los casos del chat real.

Uso (desde backend/, con IA_PROVIDER, IA_MODEL e IA_API_KEY en .env):
    uv run python -m app.ia.evaluar

Sirve para elegir entre Gemini y Groq (sección 13 de PLANEACION.md): se corre con cada uno y
se comparan aciertos y tiempos. No usa la BD: lee el menú de SEED_FILE.
"""

import sys
import time

from app.config import settings
from app.ia.casos import CASOS
from app.ia.proveedores import ErrorIA, crear_proveedor
from app.ia.servicio import interpretar
from app.menu.schema import cargar_menu


def main() -> int:
    menu = cargar_menu(settings.seed_file)
    proveedor = crear_proveedor(settings)
    print(f"IA: {settings.ia_provider} / {settings.ia_model} — {len(CASOS)} casos del chat real\n")

    aciertos = 0
    for caso in CASOS:
        inicio = time.perf_counter()
        try:
            resultado = interpretar(proveedor, menu, caso.mensaje, caso.carrito, caso.estado)
            fallo = caso.verificar(resultado, menu)
        except ErrorIA as e:
            fallo = f"error: {e}"
        segundos = time.perf_counter() - inicio
        aciertos += fallo is None
        estado = "OK   " if fallo is None else "FALLA"
        print(f"{estado} {caso.nombre:<22} {segundos:5.1f}s  {fallo or ''}")

    print(f"\n{aciertos}/{len(CASOS)} casos correctos")
    return 0 if aciertos == len(CASOS) else 1


if __name__ == "__main__":
    sys.exit(main())
