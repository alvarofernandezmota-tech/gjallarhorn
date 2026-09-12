"""La demo por teclado y por audio: lo unico de `recepcion` que usaba la voz.

Vivia al final de `mente/recepcion.py`, y era la **unica** linea que hacia
que el cerebro dependiera del telefono: `from telefono import voz`. Con eso
dentro, separar el cerebro a su propio repo habria creado una dependencia
circular entre los dos —el cerebro necesitando al bot de voz—, que es justo
lo que no puede pasar.

Aqui abajo esta la parte de voz; la conversacion sigue donde siempre. Es la
frontera de verdad: `mente/` decide QUE se contesta y no sabe si se oye por
un altavoz, por el teclado o por telefono.
"""

from pathlib import Path

from dueno import avisar  # noqa: F401  (lo usa avisos al arrancar)
from hugin.guardado import avisos
from hugin.guardado import datos
from hugin.mente import conocimiento
from hugin.mente.recepcion import Respuesta, atender, conversacion_de
from hugin.negocio import frases as _frases
from hugin.negocio import negocio as negocios
from telefono import voz


def llamada(audio: Path, negocio, transcriptor, locutor=None,
            carpeta_audio: Path | None = None) -> dict:
    """Un turno de llamada entero: audio → texto → respuesta → audio.

    Devuelve lo que hace falta para saber qué pasó: lo que se oyó, lo que se
    contestó y dónde quedó el audio. **Se registra el aviso siempre**, incluso
    si la síntesis de voz falla: perder el rastro de una llamada es peor que
    perder la contestación.
    """
    dicho = voz.escuchar(Path(audio), transcriptor)
    if not dicho:
        respuesta = Respuesta("Perdone, no le he oído. ¿Me lo repite?", "recado")
    else:
        respuesta = atender(dicho, negocio.conocimiento)

    if respuesta.aviso:
        avisos.registrar(respuesta.tipo_aviso, respuesta.aviso, respuesta.datos)

    salida = None
    if locutor is not None:
        destino = (carpeta_audio or Path(audio).parent) / f"{Path(audio).stem}-respuesta.wav"
        try:
            salida = voz.hablar(respuesta.texto, destino, locutor)
        except Exception as error:  # noqa: BLE001 — el motor de voz es de fuera
            avisos.registrar("fallo", f"No se pudo sintetizar la respuesta: {error}")
    return {"oido": dicho, "dicho": respuesta.texto,
            "intencion": respuesta.intencion, "audio": salida}


def main() -> int:
    """Atiende por teclado, o un audio suelto con `--audio`."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="El recepcionista")
    parser.add_argument("--negocio", default="peluqueria",
                        help=f"carpeta en negocios/ (hay: {', '.join(negocios.listar()) or 'ninguno'})")
    parser.add_argument("--audio", type=Path, help="un fichero de audio en vez del teclado")
    parser.add_argument("--hablar", action="store_true", help="contestar en voz, no en texto")
    args = parser.parse_args()

    try:
        negocio = negocios.cargar(args.negocio)
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return 1
    datos.usar(negocio)

    faltan = conocimiento.que_falta(negocio.conocimiento)
    if faltan:
        print(f"⚠️  {negocio.nombre}: sin rellenar {', '.join(faltan)}. "
              f"No podrá dar esa información.\n")
    for problema in _frases.problemas(negocio.conocimiento):
        print(f"⚠️  frases.toml: {problema}")
    for aviso_ in negocios.advertencias(negocio):
        print(f"⚠️  {aviso_}")

    locutor = voz.Piper(negocio.voz or voz.VOZ_POR_DEFECTO) if args.hablar else None

    if args.audio:
        resultado = llamada(args.audio, negocio, voz.Whisper(), locutor)
        print(f"🎙️  {resultado['oido'] or '(no se oyó nada)'}")
        print(f"  → {resultado['dicho']}")
        if resultado["audio"]:
            print(f"  🔊 {resultado['audio']}")
        return 0

    print(negocio.saludo)
    charla = conversacion_de(negocio)
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        respuesta = charla.atender(linea)
        print(f"  → {respuesta.texto}")
        if respuesta.aviso:
            print(f"     [{respuesta.tipo_aviso}] {respuesta.aviso}")
    if (quedo := charla.colgar()):
        print(f"     [cita] {quedo}")
    print(negocio.despedida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
