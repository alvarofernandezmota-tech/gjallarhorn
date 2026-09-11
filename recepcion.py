"""El recepcionista: atiende a quien llama, no a quien manda.

`cerebro.py` entiende órdenes de Álvaro a su diario —«recuérdame», «apunta
que»—. Esto es lo contrario: **alguien que no conoce el negocio, preguntando**.

Cuatro cosas que pide quien llama a un sitio así:

    precio     «¿cuánto vale un tinte?»
    cita       «¿tenéis hueco el sábado por la mañana?»
    horario    «¿a qué hora abrís?»
    recado     todo lo demás

## La regla que manda sobre todas

**Un precio sale de la tabla o no sale.** Si la tarifa no está, el agente dice
que no lo sabe y toma el recado. Nunca aproxima, nunca redondea, nunca dice
«unos 40 €». Cantar un precio equivocado por teléfono cuesta dinero y
credibilidad, y el cliente se presenta creyendo otra cosa.

Esto no depende del modelo que se use: la consulta de tarifa la resuelve
`conocimiento.buscar()`, que es una tabla, no un generativo. El LLM podrá
redactar mejor la frase, pero **el número no lo pone él**.

## Lo que sí o sí hay que decir

Si esto atiende llamadas de verdad, al que llama hay que avisarle de que habla
con un sistema automático. `SALUDO` lo lleva delante, y no es decorativo: en
España informar de eso no es opcional, y cambiarlo por un «hola, ¿en qué puedo
ayudarte?» a secas es quitar el aviso, no mejorar el texto.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import conocimiento
from midgaror import modulo

fechas = modulo("fechas")

SALUDO = ("Hola, le atiende un asistente automático. "
          "Puedo darle precios y tomarle una cita. ¿En qué puedo ayudarle?")

SIN_CONOCIMIENTO = ("Ahora mismo no tengo las tarifas cargadas. "
                    "Le tomo el recado y le devolvemos la llamada.")

# Una hora suelta del 1 al 11, sin decir si es mañana o tarde. «El jueves a las
# cinco» en una peluquería son las cinco de la TARDE, pero interpretarlo por mi
# cuenta es confirmar una cita que nadie ha pedido. Se pregunta.
HORA_AMBIGUA = re.compile(r"^(?:0?[1-9]|1[01]):")
# Marcas que quitan la duda.
DESAMBIGUA = re.compile(r"\b(ma[nñ]ana|tarde|noche|mediodia|am|pm|h)\b")
# Si no hay ningún número ni hora escrita, lo que dijo fue una franja
# («por la mañana»), no una hora. Dar una hora exacta ahí es inventarla.
NUMERO = re.compile(r"\d|\b(una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)\b")


@dataclass(frozen=True)
class Respuesta:
    """Lo que el agente dice, y lo que hay que apuntar de la llamada."""

    texto: str          # lo que se le contesta a quien llama
    intencion: str      # precio | cita | horario | recado
    aviso: str | None = None   # qué registrar en avisos.py, si procede
    tipo_aviso: str = "llamada"


PRECIO = re.compile(
    r"\b(precio|cuanto|cuesta|vale|valen|tarifa|tarifas|cobrais|cobran)\b")
CITA = re.compile(
    r"\b(cita|hueco|reservar|reserva|coger|apuntar|pedir\s+hora|"
    r"disponible|disponibilidad|libre)\b")
HORARIO = re.compile(
    r"\b(horario|abris|abren|cerrais|cierran|abierto|cerrado|"
    r"hasta\s+que\s+hora|a\s+que\s+hora)\b")


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def _seccion_faq(clave: str, base: Path | None = None) -> str:
    """El trozo de la FAQ que responde a algo. Texto tal cual, sin parafrasear."""
    texto = conocimiento._leer("faq.md", base)
    bloques = re.split(r"\n(?=\*\*)", texto)
    for bloque in bloques:
        if clave in _sin_tildes(bloque):
            cuerpo = bloque.split("\n", 1)
            return cuerpo[1].strip() if len(cuerpo) > 1 else ""
    return ""


def _responder_precio(frase: str, base: Path | None = None) -> Respuesta:
    encontrados = conocimiento.buscar(frase, base)
    if not encontrados:
        # Ni «lo más parecido» ni una horquilla. No se sabe y se dice.
        return Respuesta(
            "No tengo ese servicio en la lista de precios. Le tomo el recado y "
            "se lo confirmamos.",
            "precio",
            aviso=f"Preguntó un precio que no está en tarifas: «{frase}»",
            tipo_aviso="fallo")
    if len(encontrados) == 1:
        s = encontrados[0]
        duracion = f", unos {s['duracion']}" if s.get("duracion") else ""
        return Respuesta(f"{s['servicio']}: {s['precio']}{duracion}.", "precio",
                         aviso=f"{s['servicio']} → {s['precio']}", tipo_aviso="tarifa")
    opciones = "; ".join(f"{s['servicio']} {s['precio']}" for s in encontrados)
    return Respuesta(f"Tengo varias opciones: {opciones}. ¿Cuál le interesa?",
                     "precio", aviso=f"Preguntó precio: {opciones}", tipo_aviso="tarifa")


def _responder_cita(frase: str, base: Path | None = None) -> Respuesta:
    """Toma la petición de cita. **No confirma nada**: no hay agenda todavía.

    Prometer un hueco que nadie ha comprobado es peor que no cogerlo: el
    cliente se presenta y no hay sitio.
    """
    encontrado = fechas.interpretar(frase)
    comparable = _sin_tildes(frase)
    servicio = conocimiento.mencionado(frase, base)
    que = f" de {servicio['servicio'].lower()}" if servicio else ""

    if not encontrado:
        return Respuesta(f"Tomo nota de la cita{que}. ¿Qué día le viene bien?",
                         "cita", aviso=f"Pide cita{que}, sin día. Frase: «{frase}»",
                         tipo_aviso="cita")

    fecha, hora, _ = encontrado

    # Una hora que el cliente no ha dicho no se repite como si la hubiera
    # dicho: «el sábado por la mañana» no son las 09:00, es por la mañana.
    if hora and not NUMERO.search(comparable):
        return Respuesta(
            f"Tomo nota de la cita{que} para el {fecha}. ¿A qué hora le viene bien?",
            "cita", aviso=f"Pide cita{que} el {fecha}, sin hora concreta. "
                          f"Frase: «{frase}»", tipo_aviso="cita")

    # «A las cinco» en un negocio son las cinco de la tarde, pero eso lo
    # confirma el cliente, no yo. Confirmar una cita a las 05:00 es mandarle a
    # la puerta de madrugada.
    if hora and HORA_AMBIGUA.match(hora) and not DESAMBIGUA.search(comparable):
        return Respuesta(
            f"Tomo nota de la cita{que} para el {fecha}. "
            f"¿Las {int(hora[:2])} de la tarde?",
            "cita", aviso=f"Pide cita{que} el {fecha} a las {hora} — HORA SIN "
                          f"CONFIRMAR. Frase: «{frase}»", tipo_aviso="cita")

    cuando = f" para el {fecha}" + (f" a las {hora}" if hora else "")
    return Respuesta(
        f"Tomo nota de la cita{que}{cuando}. Se la confirmamos enseguida.",
        "cita", aviso=f"Pide cita{que}{cuando}. Frase: «{frase}»", tipo_aviso="cita")


def atender(frase: str, base: Path | None = None) -> Respuesta:
    """Qué contesta el recepcionista a lo que acaba de decir quien llama.

    Esta firma es la que tendría que respetar un LLM el día que sustituya a
    estas reglas — igual que `cerebro.decidir` en el lado del diario.
    """
    limpia = (frase or "").strip()
    if not limpia:
        return Respuesta("Perdone, no le he oído. ¿Me lo repite?", "recado")

    comparable = _sin_tildes(limpia)

    # La cita va antes que el precio: «quiero cita para un tinte» lleva las dos
    # palabras, y lo que quiere es la cita.
    if CITA.search(comparable):
        return _responder_cita(limpia, base)

    if PRECIO.search(comparable):
        if not conocimiento.tarifas(base):
            return Respuesta(SIN_CONOCIMIENTO, "precio",
                             aviso=f"Sin tarifas cargadas. Preguntó: «{limpia}»",
                             tipo_aviso="fallo")
        return _responder_precio(limpia, base)

    if HORARIO.search(comparable):
        respuesta = _seccion_faq("horario", base)
        if respuesta:
            return Respuesta(respuesta, "horario")
        return Respuesta(
            "No tengo el horario a mano. Le tomo el recado y le llamamos.",
            "horario", aviso="Preguntó el horario y no está en la FAQ",
            tipo_aviso="fallo")

    # Todo lo demás: no se improvisa, se apunta. Un recepcionista que se
    # inventa respuestas es peor que uno que toma recados.
    return Respuesta(
        "Tomo nota y le devolvemos la llamada en cuanto podamos.",
        "recado", aviso=f"Recado: «{limpia}»")


def main() -> int:
    """Una conversación de prueba por teclado, sin teléfono ni modelo."""
    import sys

    if not conocimiento.esta_configurado():
        print(f"⚠️  Sin conocimiento cargado: falta {', '.join(conocimiento.que_falta())}")
        print("   Prueba con: GJALLARHORN_CONOCIMIENTO=ejemplos/peluqueria\n")
    print(SALUDO)
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        respuesta = atender(linea)
        print(f"  → {respuesta.texto}")
        if respuesta.aviso:
            print(f"     [{respuesta.tipo_aviso}] {respuesta.aviso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
