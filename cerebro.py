"""El LLM, opcional, para lo que las reglas no entienden. Nunca para el precio.

Las reglas de `recepcion.py` cubren cuatro intenciones y todo lo demas acaba
en «tomo nota». Funciona y no se inventa nada, pero «oye, que me han dicho
que haceis lo del alisado ese, ¿lo teneis?» se pierde en un recado.

Aqui entra Claude **solo cuando las reglas no han entendido**, y solo para
devolver datos con forma fija:

    intencion   precio | cita | horario | despedida | otro
    servicio    uno de los nombres de la tabla de tarifas, o ninguno
    cuando      «el jueves a las cinco», tal cual lo dijo, para fechas.py
    nombre      si lo dio

Lo que hace `recepcion.py` con eso es lo mismo que haria con una frase que
las reglas si entienden: el precio sale de la tabla, la fecha la resuelve
`fechas.py`, la agenda decide si cabe. **El modelo no redacta lo que se le
dice al cliente y no pone ningun numero.** Es la regla de la casa, y la forma
de garantizarla es que su salida sea un JSON de cuatro campos, no una frase.

## Apagado por defecto

Con la clave (`ANTHROPIC_API_KEY` en `.env`) se enciende; sin ella, las
reglas solas, como hasta ahora. Y encenderlo tiene un precio que hay que
decir: **el texto de lo que dijo el cliente sale de casa** hacia la API. El
audio no; el texto si. Es una decision del dueño del negocio, no de este
fichero, y por eso no viene puesto.

## Si falla, no pasa nada

Sin red, con la clave mal, con el modelo tardando: se devuelve None y las
reglas siguen como si el LLM no existiera. Una llamada nunca se cae por esto.
El tope de tiempo es corto a proposito —una pausa de cuatro segundos al
telefono ya es larga— y se mide en cada llamada para verlo en los avisos.
"""

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import conocimiento

MODELO_POR_DEFECTO = "claude-opus-5"
TOPE_SEGUNDOS = 4.0
INTENCIONES = ("precio", "cita", "horario", "despedida", "otro")

_cliente = None


@dataclass(frozen=True)
class Entendido:
    intencion: str
    servicio: str | None = None
    cuando: str | None = None
    nombre: str | None = None
    ms: float = 0.0


def configurado() -> bool:
    """¿Hay clave? Sin ella, esto no existe."""
    import avisar
    avisar._leer_env()
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def modelo() -> str:
    return os.environ.get("GJALLARHORN_LLM_MODELO", "").strip() or MODELO_POR_DEFECTO


def _esquema(servicios: list[str]) -> dict:
    """La forma fija de la respuesta. `servicio` solo puede ser uno de la tabla."""
    return {
        "type": "object",
        "properties": {
            "intencion": {"type": "string", "enum": list(INTENCIONES)},
            "servicio": {"type": ["string", "null"], "enum": [*servicios, None]},
            "cuando": {"type": ["string", "null"]},
            "nombre": {"type": ["string", "null"]},
        },
        "required": ["intencion", "servicio", "cuando", "nombre"],
        "additionalProperties": False,
    }


def _instrucciones(servicios: list[str]) -> str:
    lista = "\n".join(f"- {s}" for s in servicios) or "- (no hay servicios cargados)"
    return (
        "Eres el clasificador de un recepcionista telefónico de un negocio en "
        "España. Te llega lo que acaba de decir quien llama, transcrito por voz "
        "(puede traer errores de transcripción). Devuelve SOLO el JSON pedido.\n\n"
        "intencion:\n"
        "- precio: pregunta cuánto cuesta algo\n"
        "- cita: quiere reservar, pedir hora, saber si hay hueco\n"
        "- horario: pregunta cuándo abrís o cerráis\n"
        "- despedida: se despide o da las gracias para colgar\n"
        "- otro: cualquier otra cosa\n\n"
        "servicio: el servicio de esta lista al que se refiere, escrito EXACTAMENTE "
        "como aparece, o null si no se refiere a ninguno o no está en la lista. "
        "Nunca inventes uno ni elijas el más parecido si no es claramente ese:\n"
        f"{lista}\n\n"
        "cuando: el trozo literal de la frase que dice el día y/o la hora "
        "(«el jueves a las cinco», «mañana por la tarde»), o null.\n"
        "nombre: el nombre de la persona si lo dice, o null."
    )


def _preguntar_claude(frase: str, servicios: list[str]) -> dict:
    """La llamada a la API. Separada para poder sustituirla en las pruebas."""
    global _cliente
    import anthropic

    if _cliente is None:
        _cliente = anthropic.Anthropic(timeout=TOPE_SEGUNDOS, max_retries=0)

    respuesta = _cliente.beta.messages.create(
        model=modelo(),
        max_tokens=256,
        system=_instrucciones(servicios),
        messages=[{"role": "user", "content": frase}],
        output_config={"effort": "low",
                       "format": {"type": "json_schema", "schema": _esquema(servicios)}},
        # Si el modelo declina por politica, que conteste otro en la misma
        # llamada en vez de dejar al cliente sin respuesta.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if respuesta.stop_reason == "refusal":
        raise RuntimeError("el modelo declinó la petición")
    texto = next(b.text for b in respuesta.content if b.type == "text")
    return json.loads(texto)


def entender(frase: str, base: Path | None = None, preguntar=None) -> Entendido | None:
    """Qué quiere quien llama, según el modelo. None si no hay modelo o falla.

    `preguntar` es la función que habla con la API; se cambia en las pruebas
    por una que devuelve lo que se le diga.
    """
    if preguntar is None:
        if not configurado():
            return None
        preguntar = _preguntar_claude

    servicios = [s["servicio"] for s in conocimiento.tarifas(base)]
    arranque = time.perf_counter()
    try:
        crudo = preguntar(frase, servicios)
    except Exception as error:  # noqa: BLE001 — red, clave, modelo: nada de esto tumba una llamada
        print(f"⚠️  el LLM no contestó ({type(error).__name__}: {error}); "
              "siguen las reglas solas", file=sys.stderr)
        return None
    ms = (time.perf_counter() - arranque) * 1000

    intencion = crudo.get("intencion")
    if intencion not in INTENCIONES:
        return None
    servicio = crudo.get("servicio")
    if servicio not in servicios:
        # Un servicio que no esta en la tabla no existe, diga lo que diga el
        # modelo. Es la regla que impide cantar un precio de algo inventado.
        servicio = None
    return Entendido(intencion=intencion, servicio=servicio,
                     cuando=(crudo.get("cuando") or None),
                     nombre=(crudo.get("nombre") or None), ms=ms)


def main() -> int:
    """`python3 cerebro.py "frase"`: qué entiende el modelo, y cuánto tarda."""
    import argparse

    import negocio as negocios

    parser = argparse.ArgumentParser(description="Qué entiende el LLM de una frase")
    parser.add_argument("frase", nargs="?", default="oye, ¿hacéis lo del alisado ese?")
    parser.add_argument("--negocio", default="peluqueria")
    args = parser.parse_args()

    if not configurado():
        print("Sin ANTHROPIC_API_KEY en .env: el LLM está apagado y las reglas van solas.")
        print("Ponerla enciende el LLM, y con él el TEXTO de lo que dice el cliente")
        print("sale de casa hacia la API. El audio no. Es decisión del negocio.")
        return 1
    n = negocios.cargar(args.negocio)
    print(f"modelo {modelo()} · «{args.frase}»")
    entendido = entender(args.frase, n.conocimiento)
    if entendido is None:
        print("❌ sin respuesta (mira el aviso de arriba)")
        return 1
    print(f"   intención {entendido.intencion} · servicio {entendido.servicio} · "
          f"cuándo {entendido.cuando!r} · nombre {entendido.nombre} · {entendido.ms:.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
