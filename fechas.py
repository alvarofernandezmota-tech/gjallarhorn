"""Cuándo quiere la cita quien llama. Siempre hacia delante.

Este parser es propio. Durante unas horas se importaba el de otro repo, y hay
un motivo de diseño para no hacerlo —además del de no depender de nadie—:

**El parser de un diario resuelve hacia atrás por defecto.** Un diario habla
del pasado: «el lunes» es el lunes que pasó. Un recepcionista es al revés:
**nadie reserva cita para el martes pasado**. Reusar uno de diario aquí era
heredar exactamente la suposición contraria a la buena.

## Qué entiende

    hoy · mañana · pasado mañana
    el jueves · este jueves · el jueves que viene
    el 15 · el 15 de octubre
    a las 5 · a las cinco · a las 17:30 · a las cinco y media

## Qué NO hace, a propósito

**Adivinar.** Lo que no encaja devuelve `None` y el recepcionista pregunta. En
una cita, preguntar cuesta una frase; equivocarse cuesta que alguien se
presente el día que no era.

Tampoco decide si «a las cinco» son las 17:00. Devuelve `05:00` y marca que la
hora venía sin franja: **quien confirma es el cliente**, no esto. Es la regla
que evitó mandar a alguien a la puerta de un negocio cerrado de madrugada.
"""

import re
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("Europe/Madrid")

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

NUMEROS = {
    "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
}

# Las franjas quitan la ambigüedad de «a las cinco», y por eso se detectan
# aparte: lo que importa no es a qué hora las traduzcas, sino si están.
FRANJAS = {"manana": "mañana", "tarde": "tarde", "noche": "noche",
           "mediodia": "mediodía"}


def ahora() -> datetime:
    """El momento actual en Madrid. Un solo reloj, como en el resto del mundo."""
    return datetime.now(ZONA)


def hoy() -> str:
    """La fecha de hoy en Madrid, `AAAA-MM-DD`."""
    return ahora().strftime("%Y-%m-%d")


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def _dia_de_la_semana(nombre: str, desde: date, que_viene: bool) -> date:
    """El próximo `nombre` a partir de `desde`, hoy incluido.

    «Hoy incluido» es deliberado: si alguien llama un jueves por la mañana y
    dice «el jueves», lo más probable es que quiera hoy. El recepcionista
    pregunta la hora de todas formas, así que si se equivoca se ve enseguida.
    `que viene` fuerza saltar a la semana siguiente.
    """
    objetivo = DIAS.index(nombre)
    salto = (objetivo - desde.weekday()) % 7
    if que_viene and salto == 0:
        salto = 7
    elif que_viene:
        salto += 7 if salto < 7 else 0
    return desde + timedelta(days=salto)


def _buscar_fecha(texto: str, hoy_: date) -> tuple[date, str] | None:
    """(fecha, trozo que la expresaba), o None si no dice ningún día."""
    if m := re.search(r"\bpasado\s+manana\b", texto):
        return hoy_ + timedelta(days=2), m.group(0)
    if m := re.search(r"\bmanana\b", texto):
        # «mañana» es el día siguiente; «por la mañana» es una franja. La
        # preposición delante es lo único que las distingue.
        if not re.search(r"\b(por|de|la|esta)\s+manana\b", texto):
            return hoy_ + timedelta(days=1), m.group(0)
    if m := re.search(r"\bhoy\b", texto):
        return hoy_, m.group(0)

    if m := re.search(rf"\b(?:el|este|proximo)?\s*({'|'.join(DIAS)})"
                      r"(\s+que\s+viene|\s+proximo)?\b", texto):
        return _dia_de_la_semana(m.group(1), hoy_, bool(m.group(2))), m.group(0)

    if m := re.search(rf"\bel\s+(\d{{1,2}})(?:\s+de\s+({'|'.join(MESES)}))?\b", texto):
        dia = int(m.group(1))
        mes = MESES.index(m.group(2)) + 1 if m.group(2) else hoy_.month
        anio = hoy_.year
        try:
            encontrada = date(anio, mes, dia)
        except ValueError:
            return None
        # Un día que ya pasó, dicho sin mes, es del mes que viene: nadie pide
        # cita para el 3 si hoy es 20.
        if encontrada < hoy_ and not m.group(2):
            mes, anio = (1, anio + 1) if mes == 12 else (mes + 1, anio)
            try:
                encontrada = date(anio, mes, dia)
            except ValueError:
                return None
        return encontrada, m.group(0)
    return None


def _buscar_hora(texto: str) -> tuple[str, bool, str] | None:
    """(hora, ¿venía con franja?, trozo), o None.

    El segundo campo es el que importa: dice si «las cinco» las acotó el
    cliente o no. Sin él, alguien acaba citado a las 05:00.
    """
    franja = next((f for f in FRANJAS if re.search(rf"\b{f}\b", texto)), None)

    if m := re.search(r"\ba\s+las?\s+(\d{1,2})[:.](\d{2})\b", texto):
        return f"{int(m.group(1)):02d}:{m.group(2)}", True, m.group(0)
    if m := re.search(r"\ba\s+las?\s+(\d{1,2})\s*h\b", texto):
        return f"{int(m.group(1)):02d}:00", True, m.group(0)

    palabras = "|".join(NUMEROS)
    if m := re.search(rf"\ba\s+las?\s+(\d{{1,2}}|{palabras})"
                      r"(\s+y\s+media|\s+y\s+cuarto)?\b", texto):
        crudo = m.group(1)
        hora = int(crudo) if crudo.isdigit() else NUMEROS[crudo]
        minutos = 30 if (m.group(2) or "").strip() == "y media" else \
                  15 if (m.group(2) or "").strip() == "y cuarto" else 0
        # Con franja de tarde o noche, «las cinco» son las 17:00. Sin franja
        # NO se traduce: se devuelve tal cual y se marca como sin acotar.
        hora = acotar(f"{hora:02d}:{minutos:02d}", franja)
        return hora, bool(franja), m.group(0)
    return None


def acotar(hora: str, franja: str | None) -> str:
    """«Las cinco» con «tarde» son las 17:00. Sin franja se devuelve tal cual.

    «Las dos del mediodía» son las 14:00: el mediodía va de las doce a las
    tres, y antes se apuntaba a las 02:00 dándolo por acotado. Por la
    mañana no se toca nada.
    """
    h, m = hora.split(":")
    h = int(h)
    if franja in ("tarde", "noche") and h < 12:
        h += 12
    elif franja == "mediodia" and h < 4:
        h += 12
    return f"{h:02d}:{m}"


# Como se dice cada franja al repetirsela a quien la ha dicho.
FRANJAS_DICHAS = {"manana": "por la mañana", "tarde": "por la tarde",
                  "noche": "por la noche", "mediodia": "a mediodía"}


def franja_en(frase: str) -> str | None:
    """La franja que dice la frase («por la tarde»), aunque no diga hora.

    Con preposición delante, siempre: «mañana» a secas es el día siguiente,
    no la franja. Sirve para recordarla: quien dice «el jueves por la tarde»
    y luego «a las cinco» ya ha dicho que son las cinco de la tarde, y
    volver a preguntárselo es no haberle escuchado.
    """
    texto = sin_tildes(frase or "")
    for franja in FRANJAS:
        if re.search(rf"\b(?:por|de|a|al|esta|este)\s+(?:la\s+|el\s+)?{franja}\b", texto):
            return franja
    return None


# ---- decirlo, que es distinto de entenderlo -----------------------------
#
# Por teclado, «2026-09-17» se lee de un vistazo. Por telefono es una ristra de
# numeros: Piper lee «dos mil veintiseis guion cero nueve guion diecisiete» y
# quien llama no se entera de que es el jueves. Un recepcionista dice «el
# jueves 17 de septiembre», asi que eso es lo que hay que decir.

DIAS_DICHOS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado",
               "domingo"]
MESES_DICHOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
HORAS_DICHAS = ["doce", "una", "dos", "tres", "cuatro", "cinco", "seis",
                "siete", "ocho", "nueve", "diez", "once"]


def en_palabras(fecha: str, hoy_: date | None = None) -> str:
    """`2026-09-17` → «el jueves 17 de septiembre». Y «hoy» y «mañana» si lo son.

    Decir «mañana» cuando es mañana no es un adorno: es lo que hace que quien
    llama sepa de qué día se habla sin tener que contar.
    """
    try:
        dia = date.fromisoformat(fecha)
    except (TypeError, ValueError):
        return str(fecha)

    hoy_ = hoy_ or ahora().date()
    if dia == hoy_:
        return "hoy"
    if dia == hoy_ + timedelta(days=1):
        return "mañana"
    if dia == hoy_ + timedelta(days=2):
        return "pasado mañana"

    dicho = f"el {DIAS_DICHOS[dia.weekday()]} {dia.day}"
    # El mes solo si no es obvio: dentro de la semana que viene, sobra.
    if (dia - hoy_).days > 7 or dia.month != hoy_.month:
        dicho += f" de {MESES_DICHOS[dia.month - 1]}"
    return dicho


def hora_en_palabras(hora: str) -> str:
    """`17:00` → «las cinco de la tarde». Con la franja, que es lo que importa.

    Devolver «las 17:00» obliga al que escucha a traducir, y devolverlo sin
    franja reabre justo la ambigüedad que se acaba de cerrar preguntando.
    """
    try:
        h, m = (int(parte) for parte in hora.split(":"))
    except (AttributeError, ValueError):
        return str(hora)

    franja = ("de la mañana" if h < 12 else "del mediodía" if h == 12
              else "de la tarde" if h < 21 else "de la noche")
    dicha = HORAS_DICHAS[h % 12]
    articulo = "la" if h % 12 == 1 else "las"

    if m == 0:
        minutos = ""
    elif m == 15:
        minutos = " y cuarto"
    elif m == 30:
        minutos = " y media"
    else:
        minutos = f" y {m}"
    return f"{articulo} {dicha}{minutos} {franja}"


def hora_suelta(frase: str) -> tuple[str, bool] | None:
    """(hora, ¿acotada?) de una frase que solo dice la hora, o None.

    «A las cinco» a secas no es una cita —eso lo sigue diciendo `interpretar`,
    devolviendo None sin día—. Pero en mitad de una conversación **sí** lo es:
    el día se dijo dos frases antes y quien lleva la cuenta lo recuerda. Esta
    función es solo el trozo de reconocer la hora, sin opinar sobre si basta.
    """
    encontrada = _buscar_hora(sin_tildes(frase or ""))
    return (encontrada[0], encontrada[1]) if encontrada else None


def interpretar(frase: str, ahora_=None) -> tuple[str, str | None, bool, str] | None:
    """(fecha, hora, ¿hora acotada?, resto de la frase), o None si no dice cuándo.

    `None` cuando no hay ningún día reconocible: una hora suelta sin día no es
    una cita, es media cita, y media cita se pregunta.
    """
    texto = sin_tildes(frase or "")
    hoy_ = (ahora_ or ahora()).date()

    encontrada = _buscar_fecha(texto, hoy_)
    if encontrada is None:
        return None
    fecha, trozo_fecha = encontrada

    hora, acotada, trozo_hora = None, False, ""
    if (h := _buscar_hora(texto)) is not None:
        hora, acotada, trozo_hora = h

    resto = texto
    for trozo in (trozo_fecha, trozo_hora):
        if trozo:
            resto = resto.replace(trozo, " ", 1)
    resto = re.sub(r"\s+", " ", resto).strip(" ,.")
    return fecha.isoformat(), hora, acotada, resto
