"""El recepcionista: atiende a quien llama.

Quien descuelga no recibe órdenes de nadie que conozca el negocio: recibe
preguntas de alguien que **no** lo conoce, y que no repite lo que ya ha dicho.

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

## Dos formas de usarlo, y la buena es la segunda

`atender()` contesta a **una** frase, sin memoria. Sirve para probar una
respuesta suelta y es lo que usan la mitad de las pruebas.

`Conversacion` es una llamada entera y **recuerda**. Es la diferencia entre un
recepcionista y un contestador:

    — ¿Cuánto vale un tinte?   → Tinte: 45 €, unos 90 min.
    — Vale, quiero cita        → Muy bien, una cita de tinte. ¿Qué día?
    — El jueves                → ¿A qué hora le viene bien?
    — A las cinco              → ¿Las 5 de la tarde?
    — Sí                       → ¿A nombre de quién?
    — Álvaro                   → Le apunto un tinte el jueves a las 17:00…

Sin memoria, el segundo turno ya pierde que era un tinte y el cuarto se cae
del todo: «a las cinco» sin día no es una cita, y sin nadie que recuerde el
día, no hay forma de que lo sea.

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

import avisos
import conocimiento
import fechas
import negocio as negocios
import voz

SALUDO = ("Hola, le atiende un asistente automático. "
          "Puedo darle precios y tomarle una cita. ¿En qué puedo ayudarle?")

SIN_CONOCIMIENTO = ("Ahora mismo no tengo las tarifas cargadas. "
                    "Le tomo el recado y le devolvemos la llamada.")


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


def _precio_de(servicio: dict) -> Respuesta:
    """Un servicio y su precio, dicho igual se llegue por donde se llegue."""
    duracion = f", unos {servicio['duracion']}" if servicio.get("duracion") else ""
    return Respuesta(f"{servicio['servicio']}: {servicio['precio']}{duracion}.",
                     "precio", aviso=f"{servicio['servicio']} → {servicio['precio']}",
                     tipo_aviso="tarifa")


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
        return _precio_de(encontrados[0])
    opciones = "; ".join(f"{s['servicio']} {s['precio']}" for s in encontrados)
    return Respuesta(f"Tengo varias opciones: {opciones}. ¿Cuál le interesa?",
                     "precio", aviso=f"Preguntó precio: {opciones}", tipo_aviso="tarifa")


def _responder_cita(frase: str, base: Path | None = None) -> Respuesta:
    """Toma la petición de cita. **No confirma nada**: no hay agenda todavía.

    Prometer un hueco que nadie ha comprobado es peor que no cogerlo: el
    cliente se presenta y no hay sitio.
    """
    encontrado = fechas.interpretar(frase)
    servicio = conocimiento.mencionado(frase, base)
    que = f" de {servicio['servicio'].lower()}" if servicio else ""

    if not encontrado:
        return Respuesta(f"Tomo nota de la cita{que}. ¿Qué día le viene bien?",
                         "cita", aviso=f"Pide cita{que}, sin día. Frase: «{frase}»",
                         tipo_aviso="cita")

    fecha, hora, acotada, _ = encontrado

    # Sin hora: el parser no se inventa ninguna, así que no hay nada que
    # deshacer. «El sábado por la mañana» llega aquí sin hora.
    if not hora:
        return Respuesta(
            f"Tomo nota de la cita{que} para el {fecha}. ¿A qué hora le viene bien?",
            "cita", aviso=f"Pide cita{que} el {fecha}, sin hora concreta. "
                          f"Frase: «{frase}»", tipo_aviso="cita")

    # Hora sin acotar: «a las cinco» en un negocio son las cinco de la tarde,
    # pero eso lo confirma el cliente, no yo. Confirmar una cita a las 05:00
    # es mandarle a la puerta de madrugada.
    if not acotada and int(hora[:2]) < 12:
        return Respuesta(
            f"Tomo nota de la cita{que} para el {fecha}. "
            f"¿Las {int(hora[:2])} de la tarde?",
            "cita", aviso=f"Pide cita{que} el {fecha} a las {hora} — HORA SIN "
                          f"CONFIRMAR. Frase: «{frase}»", tipo_aviso="cita")

    cuando = f" para el {fecha}" + (f" a las {hora}" if hora else "")
    return Respuesta(
        f"Tomo nota de la cita{que}{cuando}. Se la confirmamos enseguida.",
        "cita", aviso=f"Pide cita{que}{cuando}. Frase: «{frase}»", tipo_aviso="cita")


def _responder_horario(frase: str, base: Path | None = None) -> Respuesta:
    """El horario, tal cual está escrito en la FAQ. Sin parafrasear."""
    respuesta = _seccion_faq("horario", base)
    if respuesta:
        return Respuesta(respuesta, "horario")
    return Respuesta("No tengo el horario a mano. Le tomo el recado y le llamamos.",
                     "horario", aviso="Preguntó el horario y no está en la FAQ",
                     tipo_aviso="fallo")


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
        return _responder_horario(limpia, base)

    # Todo lo demás: no se improvisa, se apunta. Un recepcionista que se
    # inventa respuestas es peor que uno que toma recados.
    return Respuesta(
        "Tomo nota y le devolvemos la llamada en cuanto podamos.",
        "recado", aviso=f"Recado: «{limpia}»")


# ---- la llamada entera, con memoria ------------------------------------

# Lo que se acepta como «sí» y como «no» cuando se acaba de preguntar algo.
# Solo se miran cuando hay una pregunta en el aire: fuera de ahí, «no» aparece
# en media conversación («no sé», «no me va bien») y tomarlo por una respuesta
# es peor que ignorarlo.
SI = re.compile(r"^\W*(si|sip|claro|eso es|correcto|exacto|vale|perfecto|"
                r"por la tarde|de la tarde)\b")
NO = re.compile(r"^\W*(no|nop|que va|negativo|por la manana|de la manana)\b")

# «Me llamo Álvaro». Sobre el texto original, no sobre el de comparar, para no
# devolverle el nombre sin tildes a quien acaba de decirlo.
NOMBRE = re.compile(
    r"\b(?:me\s+llamo|mi\s+nombre\s+es|a\s+nombre\s+de|de\s+parte\s+de|"
    r"para\s+(?:el\s+se[nñ]or|la\s+se[nñ]ora)\s+de)\s+"
    r"([^\W\d_]+(?:\s+[^\W\d_]+)?)", re.IGNORECASE | re.UNICODE)

# Palabras que nunca son un nombre, por mucho que vayan detrás de «soy».
NO_ES_NOMBRE = {"un", "una", "el", "la", "los", "las", "mi", "su", "para",
                "que", "de", "del", "por", "cliente", "nueva", "nuevo"}

COLGAR = re.compile(r"\b(adios|hasta luego|gracias|nada mas|ya esta|"
                    r"eso es todo|colgar|chao)\b")


def _ambigua(hora: str, acotada: bool) -> bool:
    """¿«Las cinco» podrían ser las 17:00 y nadie lo ha dicho?

    A partir de las 12 no hay duda: «las 17» son las 17. La ambigüedad solo
    existe por debajo, y es la que manda a alguien a la puerta de madrugada.
    """
    return not acotada and int(hora[:2]) < 12


def _nombre_en(frase: str) -> str | None:
    """El nombre que se acaba de dar, si se ha dado con todas las letras."""
    if (m := NOMBRE.search(frase)) is None:
        return None
    nombre = " ".join(m.group(1).split())
    if nombre.split()[0].lower() in NO_ES_NOMBRE:
        return None
    return nombre.title()


def _nombre_a_secas(frase: str) -> str | None:
    """La frase entera tomada como nombre, tras preguntar «¿a nombre de quién?».

    Solo vale aquí: a esa pregunta se contesta «Álvaro», sin "me llamo"
    delante. Se descarta lo que claramente no es un nombre —cifras, preguntas,
    parrafadas— porque apuntar «pues no sé si podré ir» como nombre de cliente
    es peor que volver a preguntar.
    """
    limpio = frase.strip().strip(".,;:¿?¡!")
    limpio = re.sub(r"^(?:soy|me\s+llamo|mi\s+nombre\s+es|es|de)\s+", "",
                    limpio, flags=re.IGNORECASE)
    palabras = limpio.split()
    if not palabras or len(palabras) > 3 or any(c.isdigit() for c in limpio):
        return None
    if "?" in frase or palabras[0].lower() in NO_ES_NOMBRE:
        return None
    return " ".join(palabras).title()


@dataclass
class Cita:
    """Lo que hay que saber antes de poder apuntar a alguien."""

    servicio: str | None = None
    fecha: str | None = None
    hora: str | None = None
    acotada: bool = False
    nombre: str | None = None
    cerrada: bool = False

    def falta(self) -> str | None:
        """Lo primero que falta, en el orden en que se pregunta por teléfono."""
        if not self.fecha:
            return "fecha"
        if not self.hora:
            return "hora"
        if _ambigua(self.hora, self.acotada):
            return "franja"
        if not self.nombre:
            return "nombre"
        return None

    def resumen(self) -> str:
        """Cómo se lee esta cita en un aviso.

        Aquí la fecha va en ISO a propósito: esto lo lee quien lleva el
        negocio, no quien llamó, y `2026-09-17` no se presta a discusión.
        """
        partes = [self.servicio.lower() if self.servicio else "cita sin servicio",
                  f"el {self.fecha}" if self.fecha else "sin día",
                  f"a las {self.hora}" if self.hora else "sin hora"]
        if self.hora and _ambigua(self.hora, self.acotada):
            partes[-1] += " (SIN CONFIRMAR mañana/tarde)"
        if self.nombre:
            partes.append(f"a nombre de {self.nombre}")
        return ", ".join(partes)


class Conversacion:
    """Una llamada. Recuerda lo dicho, porque quien llama no lo repite.

    ## Por qué el aviso se registra al colgar y no en cada turno

    Una cita se construye a lo largo de cinco frases. Registrando cada turno,
    el registro de llamadas se llena de cinco apuntes —«pide cita», «pide cita
    el jueves», «pide cita el jueves a las cinco»…— de los que solo el último
    sirve, y hay que leerlos todos para saber en qué quedó.

    Así que se apunta **el resultado**: la cita cerrada, o lo que se quedó a
    medias si la llamada se corta. `colgar()` es quien lo hace, y el servidor
    lo llama al reiniciar. Perder el rastro de una llamada sigue siendo lo
    peor que puede pasar aquí, así que a medias también se apunta.
    """

    def __init__(self, base: Path | None = None):
        self.base = base
        self.cita: Cita | None = None
        self.servicio: dict | None = None     # del que se viene hablando
        self.nombre: str | None = None
        self.esperando: str | None = None     # qué se acaba de preguntar
        self.turnos: list[tuple[str, str]] = []

    # -- lo que se recuerda de cada frase, se pregunte lo que se pregunte ----

    def _recordar(self, frase: str) -> dict | None:
        """Guarda lo que aporte esta frase. Devuelve el servicio que nombra AHORA.

        La distinción entre «el que nombra ahora» y «el que se recuerda» no es
        sutileza: confundirlos hace que a «¿y cambiar el parabrisas?» se le
        conteste con el precio del tinte de hace dos turnos. Es decir, cantar
        el precio de un servicio que no existe, que es justo lo que esto no
        puede hacer nunca.
        """
        servicio = conocimiento.mencionado(frase, self.base)
        if servicio is not None:
            self.servicio = servicio
            if self.cita and not self.cita.cerrada:
                self.cita.servicio = servicio["servicio"]
        if (nombre := _nombre_en(frase)) is not None:
            self.nombre = nombre
            if self.cita and not self.cita.cerrada:
                self.cita.nombre = nombre
        return servicio

    # -- la cita, turno a turno ---------------------------------------------

    def _abrir_cita(self) -> Cita:
        self.cita = Cita(servicio=self.servicio["servicio"] if self.servicio else None,
                         nombre=self.nombre)
        return self.cita

    def _seguir_cita(self) -> Respuesta:
        """La siguiente pregunta, o el cierre si ya no falta nada."""
        cita = self.cita
        que = f" de {cita.servicio.lower()}" if cita.servicio else ""
        self.esperando = falta = cita.falta()

        if falta == "fecha":
            return Respuesta(f"Muy bien, una cita{que}. ¿Qué día le viene bien?", "cita")
        if falta == "hora":
            return Respuesta(f"Perfecto, {fechas.en_palabras(cita.fecha)}. "
                             "¿A qué hora le viene bien?", "cita")
        if falta == "franja":
            # No se resuelve sola: confirmarla es de quien llama. Es la regla
            # que evita citar a nadie a las cinco de la madrugada.
            dicha = fechas.hora_en_palabras(f"{int(cita.hora[:2]) + 12:02d}:{cita.hora[3:]}")
            return Respuesta(f"¿{dicha[0].upper()}{dicha[1:]}?", "cita")
        if falta == "nombre":
            return Respuesta("¿A nombre de quién se la apunto?", "cita")

        cita.cerrada = True
        self.esperando = None
        # Se apunta, no se confirma: aquí no hay agenda que consultar todavía,
        # y prometer un hueco que nadie ha mirado es peor que no cogerlo.
        return Respuesta(
            f"Perfecto. Le apunto la cita{que} {fechas.en_palabras(cita.fecha)} "
            f"a {fechas.hora_en_palabras(cita.hora)}, a nombre de {cita.nombre}. "
            "Se lo confirmamos enseguida.", "cita")

    def _rellenar_con(self, frase: str) -> bool:
        """Mete en la cita lo que traiga esta frase. ¿Ha aportado algo?"""
        cita, puesto = self.cita, False

        if not cita.fecha and (encontrado := fechas.interpretar(frase)) is not None:
            cita.fecha, hora, acotada, _ = encontrado
            puesto = True
            if hora and not cita.hora:
                cita.hora, cita.acotada = hora, acotada
        elif cita.fecha and not cita.hora and (h := fechas.hora_suelta(frase)) is not None:
            cita.hora, cita.acotada = h
            puesto = True

        if self.esperando == "nombre" and not cita.nombre:
            if (nombre := _nombre_a_secas(frase)) is not None:
                cita.nombre = self.nombre = nombre
                puesto = True
        return puesto

    def _confirmar_franja(self, comparable: str) -> Respuesta | None:
        """Resuelve el «¿las 5 de la tarde?» que se acaba de preguntar."""
        cita = self.cita
        if SI.search(comparable):
            cita.hora = f"{int(cita.hora[:2]) + 12:02d}:{cita.hora[3:]}"
            cita.acotada = True
            return self._seguir_cita()
        if NO.search(comparable):
            # Podría darse por la mañana, pero las 05:00 en un negocio que abre
            # a las diez no es una cita: es un error esperando a pasar.
            cita.hora, cita.acotada = None, False
            return self._seguir_cita()
        return None

    # -- el turno ------------------------------------------------------------

    def atender(self, frase: str) -> Respuesta:
        """Qué contesta el recepcionista, sabiendo lo que ya se ha dicho."""
        limpia = (frase or "").strip()
        if not limpia:
            return Respuesta("Perdone, no le he oído. ¿Me lo repite?", "recado")

        respuesta = self._decidir(limpia)
        self.turnos.append((limpia, respuesta.texto))
        return respuesta

    def _decidir(self, limpia: str) -> Respuesta:
        comparable = _sin_tildes(limpia)
        ahora_mismo = self._recordar(limpia)
        viva = self.cita is not None and not self.cita.cerrada

        # Acabo de ofrecer varias opciones y me acaban de decir cuál. Eso es
        # una pregunta de precio, aunque la frase sea solo «el tinte».
        #
        # **El servicio tiene que salir de ESTA frase**, no del que se
        # recordaba: si me preguntan por algo que no está en la tabla, la
        # respuesta es que no lo tengo, no el precio del anterior.
        if self.esperando == "cual":
            self.esperando = None
            if ahora_mismo is not None:
                return _precio_de(ahora_mismo)
            if not CITA.search(comparable) and not HORARIO.search(comparable):
                # Han nombrado algo que no está en la tabla. Decirlo es más
                # útil que un «tomo nota» genérico, y sigue sin inventarse
                # ningún precio.
                return Respuesta(
                    "No tengo ese servicio en la lista de precios. Le tomo el "
                    "recado y se lo confirmamos.", "precio",
                    aviso=f"Preguntó un precio que no está en tarifas: «{limpia}»",
                    tipo_aviso="fallo")

        if viva and self.esperando == "franja":
            if (hecho := self._confirmar_franja(comparable)) is not None:
                return hecho

        # Una frase que trae el dato que se acababa de pedir. Va antes que las
        # intenciones: «el jueves» no lleva la palabra «cita» y aun así lo es.
        if viva and self._rellenar_con(limpia):
            return self._seguir_cita()

        if CITA.search(comparable):
            self._abrir_cita()
            self._rellenar_con(limpia)
            return self._seguir_cita()

        if PRECIO.search(comparable):
            if not conocimiento.tarifas(self.base):
                return Respuesta(SIN_CONOCIMIENTO, "precio",
                                 aviso=f"Sin tarifas cargadas. Preguntó: «{limpia}»",
                                 tipo_aviso="fallo")
            respuesta = _responder_precio(limpia, self.base)
            # Si he ofrecido varias, la siguiente frase será cuál de ellas.
            self.esperando = "cual" if "¿Cuál le interesa?" in respuesta.texto else None
            return respuesta

        if HORARIO.search(comparable):
            return _responder_horario(limpia, self.base)

        if COLGAR.search(comparable):
            return Respuesta("Gracias a usted. ¡Hasta luego!", "recado")

        # Nada que reconocer. Si hay una cita a medias, se insiste con lo que
        # falta en vez de soltar un «tomo nota» que la abandona.
        if viva:
            return self._seguir_cita()
        return Respuesta("Tomo nota y le devolvemos la llamada en cuanto podamos.",
                         "recado", aviso=f"Recado: «{limpia}»")

    # -- el final ------------------------------------------------------------

    def colgar(self) -> str | None:
        """Apunta en qué quedó la llamada. Devuelve el aviso escrito, si hubo."""
        if self.cita is None:
            return None
        if self.cita.cerrada:
            texto = f"Cita: {self.cita.resumen()}"
        else:
            texto = (f"Llamada cortada con la cita a medias: "
                     f"{self.cita.resumen()}. Falta: {self.cita.falta()}")
        avisos.registrar("cita", texto)
        self.cita = None
        self.esperando = None
        return texto


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
        avisos.registrar(respuesta.tipo_aviso, respuesta.aviso)

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
    except FileNotFoundError as error:
        print(f"❌ {error}")
        return 1

    faltan = conocimiento.que_falta(negocio.conocimiento)
    if faltan:
        print(f"⚠️  {negocio.nombre}: sin rellenar {', '.join(faltan)}. "
              f"No podrá dar esa información.\n")

    locutor = voz.Piper(negocio.voz or voz.VOZ_POR_DEFECTO) if args.hablar else None

    if args.audio:
        resultado = llamada(args.audio, negocio, voz.Whisper(), locutor)
        print(f"🎙️  {resultado['oido'] or '(no se oyó nada)'}")
        print(f"  → {resultado['dicho']}")
        if resultado["audio"]:
            print(f"  🔊 {resultado['audio']}")
        return 0

    print(negocio.saludo)
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        respuesta = atender(linea, negocio.conocimiento)
        print(f"  → {respuesta.texto}")
        if respuesta.aviso:
            print(f"     [{respuesta.tipo_aviso}] {respuesta.aviso}")
    print(negocio.despedida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
