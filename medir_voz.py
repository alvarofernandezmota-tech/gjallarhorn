"""Cuánto tarda el agente en contestar. Sin teléfono, sin tarjeta, sin micrófono.

## Por qué esto va antes que la telefonía

La pata de telefonía es la parte **conocida**: un proveedor entrega la llamada
en unos cientos de milisegundos y eso no lo cambia nadie. Lo desconocido —y lo
que puede tumbar el proyecto— es **cuánto tarda Whisper en el hardware de
casa**. Un agente que tarda cuatro segundos en contestar no se usa, por bien
que acierte.

Y eso se mide **gratis**, porque el truco es que las dos mitades se dan de
comer la una a la otra: **Piper fabrica la voz del cliente y Whisper la
escucha**. Ni micrófono, ni número, ni cuenta en ningún sitio.

## Lo que mide, y lo que no

Un turno de llamada son cuatro tramos:

    [red del proveedor] → escuchar → pensar → hablar → [red del proveedor]
                         └──────── esto es lo que mide ────────┘

Lo de los extremos no está aquí: hay que sumarlo aparte cuando exista un
número. Pero si lo de en medio ya se pasa del presupuesto, la red da igual.

## El presupuesto

Un silencio de más de **dos segundos** al teléfono es cuando la gente dice
«¿hola?». Ese es el listón: si `escuchar + pensar + hablar` no cabe holgado
por debajo, esta arquitectura no vale y hay que irse a una API de voz en
tiempo real —que funciona mejor y manda el audio a un tercero, con lo que eso
implica—.

    python3 medir_voz.py --negocio peluqueria
"""

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

import negocio as negocios
import recepcion
import voz

# Un silencio mayor que esto al teléfono es cuando el cliente dice «¿hola?».
PRESUPUESTO_MS = 2000

# Lo que diría quien llama. Cortas y largas a propósito: Whisper tarda por
# duración de audio, así que una frase larga es el caso malo, no el raro.
FRASES = [
    "hola",
    "cuánto vale un corte",
    "cuánto cuesta un tinte y unas mechas",
    "quería pedir cita para el jueves por la tarde si tenéis hueco",
    "buenas, llamaba para saber si abrís los sábados y cuánto cobráis "
    "por un recogido, que tengo una boda el mes que viene",
]


def _cronometrar(funcion):
    arranque = time.perf_counter()
    resultado = funcion()
    return resultado, (time.perf_counter() - arranque) * 1000


def turno(frase: str, negocio, transcriptor, locutor, carpeta: Path) -> dict:
    """Un turno completo, con el tiempo de cada tramo.

    El audio de entrada se fabrica con el locutor: es la voz del cliente. Ese
    tiempo **no cuenta** en el total —al teléfono lo pone la persona, no la
    máquina—, pero se mide para saber si el motor de voz da o no da.
    """
    entrada = carpeta / "cliente.wav"
    _, ms_fabricar = _cronometrar(lambda: locutor.decir(frase, entrada))

    oido, ms_escuchar = _cronometrar(lambda: voz.escuchar(entrada, transcriptor))
    respuesta, ms_pensar = _cronometrar(
        lambda: recepcion.atender(oido, negocio.conocimiento))
    _, ms_hablar = _cronometrar(
        lambda: voz.hablar(respuesta.texto, carpeta / "agente.wav", locutor))

    return {
        "frase": frase,
        "oido": oido,
        "dicho": respuesta.texto,
        "ms_fabricar": ms_fabricar,
        "ms_escuchar": ms_escuchar,
        "ms_pensar": ms_pensar,
        "ms_hablar": ms_hablar,
        "ms_total": ms_escuchar + ms_pensar + ms_hablar,
    }


def informe(turnos: list[dict]) -> str:
    if not turnos:
        return "Nada que medir."
    totales = [t["ms_total"] for t in turnos]
    peor = max(turnos, key=lambda t: t["ms_total"])

    lineas = [
        f"{len(turnos)} turnos · presupuesto {PRESUPUESTO_MS} ms",
        "",
        f"{'frase':<46} {'oír':>8} {'pensar':>8} {'hablar':>8} {'TOTAL':>9}",
    ]
    for t in turnos:
        recorte = (t["frase"][:43] + "…") if len(t["frase"]) > 44 else t["frase"]
        marca = "  ⚠️" if t["ms_total"] > PRESUPUESTO_MS else ""
        lineas.append(
            f"{recorte:<46} {t['ms_escuchar']:>7.0f} {t['ms_pensar']:>8.0f} "
            f"{t['ms_hablar']:>8.0f} {t['ms_total']:>8.0f}{marca}")

    lineas += [
        "",
        f"Mediana  {statistics.median(totales):.0f} ms",
        f"Peor     {peor['ms_total']:.0f} ms  ← «{peor['frase'][:50]}»",
    ]

    # Dónde se va el tiempo. Casi siempre es oír, y saberlo dice qué tocar.
    tramos = {n: sum(t[f"ms_{n}"] for t in turnos)
              for n in ("escuchar", "pensar", "hablar")}
    total = sum(tramos.values()) or 1
    lineas.append("Reparto  " + " · ".join(
        f"{n} {v / total:.0%}" for n, v in tramos.items()))

    if max(totales) > PRESUPUESTO_MS:
        lineas += [
            "",
            "⚠️  Algún turno se pasa del presupuesto. Antes de rendirse:",
            "    un modelo de Whisper más pequeño (`--modelo base` o `tiny`),",
            "    y mirar el reparto de arriba para saber qué tramo tocar.",
            "    Si aun así no baja, esta arquitectura no vale para el teléfono.",
        ]
    else:
        lineas += ["", "✅ Cabe en el presupuesto. Falta sumarle la red del proveedor."]
    return "\n".join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cuánto tarda el agente en contestar")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--modelo", default=voz.MODELO_POR_DEFECTO,
                        help=f"modelo de Whisper (por defecto: {voz.MODELO_POR_DEFECTO})")
    parser.add_argument("--voz", default=voz.VOZ_POR_DEFECTO)
    args = parser.parse_args()

    try:
        negocio = negocios.cargar(args.negocio)
    except FileNotFoundError as error:
        print(f"❌ {error}")
        return 1

    try:
        transcriptor, locutor = voz.Whisper(args.modelo), voz.Piper(args.voz)
        with tempfile.TemporaryDirectory() as tmp:
            # Un turno en vacío antes de medir: la primera vez se carga el
            # modelo, y ese tiempo no es el de una llamada.
            carpeta = Path(tmp)
            turno("hola", negocio, transcriptor, locutor, carpeta)
            turnos = [turno(f, negocio, transcriptor, locutor, carpeta) for f in FRASES]
    except RuntimeError as error:
        print(f"❌ {error}")
        print("\n   Esto se corre en la máquina donde vaya a vivir el agente,")
        print("   que es la única cuyo tiempo importa.")
        return 1

    print(f"Whisper «{args.modelo}» · Piper «{args.voz}»\n")
    print(informe(turnos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
