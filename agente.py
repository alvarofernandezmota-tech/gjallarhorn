"""El agente entero: le hablas y hace algo. Las tres capas del ADR-018 juntas.

    audio → voz.escuchar → cerebro.decidir → acciones.ejecutar → una frase

La frase que sale es lo que el agente contesta. Hoy se lee; el día que haya
síntesis de voz, se dirá.

Desde la terminal, con un fichero de audio:

    python3 agente.py nota.ogg

O con texto, para probar el cerebro sin grabar nada:

    python3 agente.py --texto "recuérdame llamar al dentista el jueves"
"""

import argparse
import sys
from pathlib import Path

import acciones
import cerebro
import voz


def responder(frase: str) -> str:
    """Lo que el agente hace y contesta ante una frase ya transcrita.

    Un fallo de una acción **no se traga**: se convierte en una frase que lo
    dice. El agente hablando es la única interfaz que hay, así que un error
    silencioso aquí es un mensaje perdido sin que nadie se entere.
    """
    try:
        accion, argumentos = cerebro.decidir(frase)
    except ValueError as error:
        return f"No te he entendido: {error}"
    try:
        return acciones.ejecutar(accion, **argumentos)
    except Exception as error:  # noqa: BLE001 — abajo hay git, disco y JSON
        return f"He entendido «{accion}» pero no he podido: {error}"


def escuchar_y_responder(audio: Path, transcriptor: voz.Transcriptor) -> tuple[str, str]:
    """(lo que se oyó, lo que contesta el agente).

    Se devuelven las dos cosas porque la transcripción es lo primero que se
    mira cuando el agente hace algo raro: casi siempre oyó otra cosa.
    """
    dicho = voz.escuchar(audio, transcriptor)
    if not dicho:
        return "", "No he oído nada."
    return dicho, responder(dicho)


def main() -> int:
    parser = argparse.ArgumentParser(description="Háblale al diario")
    parser.add_argument("audio", nargs="?", type=Path, help="fichero de audio")
    parser.add_argument("--texto", help="saltarse la oreja y probar el cerebro")
    parser.add_argument("--modelo", default=voz.MODELO_POR_DEFECTO,
                        help=f"modelo de Whisper (por defecto: {voz.MODELO_POR_DEFECTO})")
    args = parser.parse_args()

    if args.texto:
        print(responder(args.texto))
        return 0
    if not args.audio:
        parser.error("hace falta un fichero de audio, o --texto")

    dicho, respuesta = escuchar_y_responder(args.audio, voz.Whisper(args.modelo))
    if dicho:
        print(f"🎙️  {dicho}")
    print(respuesta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
