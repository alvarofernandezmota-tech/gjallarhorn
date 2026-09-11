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
from datetime import date
from pathlib import Path

import agenda as _agenda
import avisos
import cerebro
import conocimiento
import fechas
import frases as _frases
import negocio as negocios
import voz

@dataclass(frozen=True)
class Respuesta:
    """Lo que el agente dice, y lo que hay que apuntar de la llamada."""

    texto: str          # lo que se le contesta a quien llama
    intencion: str      # precio | cita | horario | recado
    aviso: str | None = None   # qué registrar en avisos.py, si procede
    tipo_aviso: str = "llamada"


# Lo que se reconoce de quien llama vive en `frases.py` y se puede cambiar por
# negocio en `frases.toml`. Aquí no queda ni una palabra clavada: en un barrio
# a las mechas les llaman «reflejos» y eso no se arregla tocando Python.


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


def _entre_ofrecidos(frase: str, ofrecidos: list[dict]) -> dict | None:
    """Cuál de los servicios ofrecidos nombra la frase, por sus palabras.

    Entre «Corte de caballero» y «Corte de señora», «el de caballero» solo
    comparte una palabra con el primero: basta. La búsqueda general exige
    cubrir más de la mitad del nombre y aquí fallaba —«caballero» es 1 de
    2— justo cuando el cliente acaba de elegir.
    """
    dichas = conocimiento._palabras(frase)
    if not dichas:
        return None
    candidatos = [s for s in ofrecidos if dichas & conocimiento._palabras(s["servicio"])]
    if len(candidatos) != 1:
        return None
    # La palabra tiene que distinguirlo, no ser la comun a todos («corte»).
    comunes = set.intersection(*(conocimiento._palabras(s["servicio"]) for s in ofrecidos))
    return candidatos[0] if dichas & conocimiento._palabras(candidatos[0]["servicio"]) - comunes else None


def _precio_de(servicio: dict, frases) -> Respuesta:
    """Un servicio y su precio, dicho igual se llegue por donde se llegue."""
    duracion = f", unos {servicio['duracion']}" if servicio.get("duracion") else ""
    return Respuesta(
        frases.decir("precio_uno", servicio=servicio["servicio"],
                     precio=servicio["precio"], duracion=duracion),
        "precio", aviso=f"{servicio['servicio']} → {servicio['precio']}",
        tipo_aviso="tarifa")


def _responder_precio(frase: str, base: Path | None = None) -> Respuesta:
    frases = _frases.cargar(base)
    encontrados = conocimiento.buscar(frase, base)
    if not encontrados:
        # Ni «lo más parecido» ni una horquilla. No se sabe y se dice.
        return Respuesta(
            frases.decir("precio_no_esta"), "precio",
            aviso=f"Preguntó un precio que no está en tarifas: «{frase}»",
            tipo_aviso="fallo")
    if len(encontrados) == 1:
        return _precio_de(encontrados[0], frases)
    opciones = "; ".join(f"{s['servicio']} {s['precio']}" for s in encontrados)
    return Respuesta(frases.decir("precio_varios", opciones=opciones), "precio",
                     aviso=f"Preguntó precio: {opciones}", tipo_aviso="tarifa")


def _responder_cita(frase: str, base: Path | None = None) -> Respuesta:
    """La versión de una sola frase: toma nota y **no confirma nada**.

    Es la que usa `atender()` suelto, sin memoria ni agenda. La que reserva
    de verdad es `Conversacion`, que mira el horario y los huecos. Aquí,
    prometer un hueco que nadie ha comprobado es peor que no cogerlo: el
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
    return Respuesta(_frases.cargar(base).decir("sin_horario"), "horario",
                     aviso="Preguntó el horario y no está en la FAQ",
                     tipo_aviso="fallo")


def atender(frase: str, base: Path | None = None) -> Respuesta:
    """Qué contesta el recepcionista a lo que acaba de decir quien llama.

    Esta firma es la que tendría que respetar un LLM el día que sustituya a
    estas reglas — igual que `cerebro.decidir` en el lado del diario.
    """
    limpia = (frase or "").strip()
    if not limpia:
        return Respuesta(_frases.cargar(base).decir("no_le_oigo"), "recado")

    comparable = _sin_tildes(limpia)
    frases = _frases.cargar(base)

    # La cita va antes que el precio: «quiero cita para un tinte» lleva las dos
    # palabras, y lo que quiere es la cita.
    if frases.reconoce("cita", comparable):
        return _responder_cita(limpia, base)

    if frases.reconoce("precio", comparable):
        if not conocimiento.tarifas(base):
            return Respuesta(frases.decir("sin_tarifas"), "precio",
                             aviso=f"Sin tarifas cargadas. Preguntó: «{limpia}»",
                             tipo_aviso="fallo")
        return _responder_precio(limpia, base)

    if frases.reconoce("horario", comparable):
        return _responder_horario(limpia, base)

    # Todo lo demás: no se improvisa, se apunta. Un recepcionista que se
    # inventa respuestas es peor que uno que toma recados.
    return Respuesta(frases.decir("recado"), "recado", aviso=f"Recado: «{limpia}»")


# ---- la llamada entera, con memoria ------------------------------------

# «Me llamo Álvaro». Sobre el texto original, no sobre el de comparar, para no
# devolverle el nombre sin tildes a quien acaba de decirlo.
NOMBRE = re.compile(
    r"\b(?:me\s+llamo|mi\s+nombre\s+es|a\s+nombre\s+de|de\s+parte\s+de|"
    r"para\s+(?:el\s+se[nñ]or|la\s+se[nñ]ora)\s+de)\s+"
    r"([^\W\d_]+(?:\s+[^\W\d_]+)?)", re.IGNORECASE | re.UNICODE)

# Palabras que nunca son un nombre, por mucho que vayan detrás de «soy».
NO_ES_NOMBRE = {"un", "una", "el", "la", "los", "las", "mi", "su", "para",
                "que", "de", "del", "por", "cliente", "nueva", "nuevo"}

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

    def __init__(self, base: Path | None = None, agenda=None, preguntar=None):
        self.base = base
        self.frases = _frases.cargar(base)
        self.agenda = agenda          # agenda.Agenda, o None: entonces solo toma nota
        self.preguntar = preguntar    # el LLM de cerebro.py; None = el real, si hay clave
        self.cita: Cita | None = None
        self.servicio: dict | None = None     # del que se viene hablando
        self.nombre: str | None = None
        self.esperando: str | None = None     # qué se acaba de preguntar
        self._propuesta: str | None = None    # la hora propuesta al preguntar la franja
        self._candidatas: list[dict] = []     # citas entre las que hay que elegir al anular
        self._opciones: list[dict] = []       # servicios ofrecidos en «¿cuál le interesa?»
        self._cambiando = False               # anular para poner otra, no solo anular
        self._sin_entender = 0                # seguidas; a la tercera se toma el recado
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
            return Respuesta(self.frases.decir("pide_dia", servicio=que), "cita")
        if falta == "hora":
            return Respuesta(self.frases.decir(
                "pide_hora", fecha=self._dicha(cita.fecha), servicio=que), "cita")
        if falta == "franja":
            return self._preguntar_franja()
        if falta == "nombre":
            if self.agenda is not None and (no_cabe := self._si_no_cabe(que)) is not None:
                return no_cabe
            return Respuesta(self.frases.decir("pide_nombre"), "cita")

        if self.agenda is None:
            # Sin agenda se apunta, no se confirma: prometer un hueco que
            # nadie ha mirado es peor que no cogerlo.
            cita.cerrada = True
            self.esperando = None
            return Respuesta(self.frases.decir(
                "cierra_cita", servicio=que, fecha=self._dicha(cita.fecha),
                hora=fechas.hora_en_palabras(cita.hora), nombre=cita.nombre), "cita")
        if (no_cabe := self._si_no_cabe(que)) is not None:
            # Entre la comprobacion de antes y ahora ha podido entrar otra
            # llamada. Se vuelve a mirar; la agenda lo mira otra vez al reservar.
            return no_cabe
        return self._reservar(que)

    # -- anular --------------------------------------------------------------

    def _anular(self, frase: str) -> Respuesta:
        """Quitar una cita. Sin agenda se toma nota; con agenda se quita."""
        if self.agenda is None:
            self.esperando = None
            return Respuesta(self.frases.decir("sin_agenda_anular"), "cita",
                             aviso=f"Quiere anular una cita: «{frase}»", tipo_aviso="cita")
        if not self.nombre:
            self.esperando = "anular_nombre"
            return Respuesta(self.frases.decir("anular_nombre"), "cita")
        return self._anular_de(self.nombre, frase)

    def _anular_de(self, nombre: str, frase: str) -> Respuesta:
        suyas = self.agenda.citas_de(nombre)
        if not suyas:
            self.esperando = None
            return Respuesta(
                self.frases.decir("anular_no_hay", nombre=nombre), "cita",
                aviso=f"Quiso anular y no hay ninguna cita a nombre de {nombre}. "
                      f"Frase: «{frase}»", tipo_aviso="fallo")

        if (dicho := fechas.interpretar(frase, self.ahora())) is not None:
            suyas = self._del_dia(suyas, dicho[0]) or suyas

        if len(suyas) > 1:
            self._candidatas = suyas
            self.esperando = "anular_cual"
            listado = ", ".join(
                f"{self._dicha(c['fecha'])} a {fechas.hora_en_palabras(c['hora'])}"
                for c in suyas)
            return Respuesta(self.frases.decir("anular_cual", citas=listado), "cita")
        return self._quitar(suyas[0])

    @staticmethod
    def _del_dia(citas: list[dict], fecha: str) -> list[dict]:
        """Las citas de esa fecha; si no hay ninguna, las de ese día de la semana.

        Lo segundo no es un apaño: quien tiene cita el viernes que viene dice
        «la del viernes», y si hoy es viernes la fecha resuelta es **hoy**. Sin
        el respaldo por día de la semana, decir el día correcto no sirve de
        nada y hay que preguntar igual.
        """
        exactas = [c for c in citas if c["fecha"] == fecha]
        if exactas:
            return exactas
        try:
            dia = date.fromisoformat(fecha).weekday()
        except ValueError:
            return []
        mismo_dia = [c for c in citas if date.fromisoformat(c["fecha"]).weekday() == dia]
        # Solo si no hay ambigüedad: dos viernes distintos se preguntan.
        return mismo_dia if len(mismo_dia) == 1 else []

    def _elegir_candidata(self, frase: str) -> dict | None:
        """Cuál de las citas ofrecidas, por el día que diga. None si no se sabe."""
        if (dicho := fechas.interpretar(frase, self.ahora())) is None:
            return None
        encontradas = self._del_dia(self._candidatas, dicho[0])
        return encontradas[0] if len(encontradas) == 1 else None

    def _quitar(self, cita: dict) -> Respuesta:
        quitada = self.agenda.anular(cita["id"])
        self._candidatas, self.esperando = [], None
        if quitada is None:
            # Se la ha llevado otra llamada entre la pregunta y ahora.
            return Respuesta(self.frases.decir("anular_no_hay", nombre=self.nombre or ""),
                             "cita", aviso=f"Intentó anular la cita {cita['id']}, "
                                           "que ya no estaba", tipo_aviso="fallo")
        que = f" de {quitada['servicio'].lower()}" if quitada.get("servicio") else ""
        aviso = (f"ANULADA: {quitada.get('servicio') or 'cita'}, el {quitada['fecha']} "
                 f"a las {quitada['hora']}, a nombre de {quitada.get('nombre')}")

        if self._cambiando:
            # Se abre la nueva ya, para que no cuelgue sin cita ni aviso.
            self._cambiando = False
            self.cita = Cita(servicio=quitada.get("servicio"), nombre=quitada.get("nombre"))
            self.esperando = "fecha"
            return Respuesta(self.frases.decir(
                "anulada_y_otra", servicio=que,
                fecha=self._dicha(quitada["fecha"]),
                hora=fechas.hora_en_palabras(quitada["hora"])), "cita",
                aviso=aviso + " — pidió cambiarla", tipo_aviso="cita")

        return Respuesta(self.frases.decir(
            "anulada", servicio=que, fecha=self._dicha(quitada["fecha"]),
            hora=fechas.hora_en_palabras(quitada["hora"])), "cita",
            aviso=aviso, tipo_aviso="cita")

    def ahora(self):
        """El reloj de esta llamada. **Uno solo**, y por eso sale de la agenda.

        Antes `fechas.interpretar` usaba el reloj del sistema y la agenda el
        suyo. En producción coinciden, así que no se notaba; en cuanto se fija
        uno para probar, «hoy» significa un día en la conversación y otro en
        la agenda, y la cita se va a un día que nadie pidió. Dos relojes en el
        mismo sitio son un fallo esperando a que alguien los separe.
        """
        return self.agenda.ahora() if self.agenda is not None else fechas.ahora()

    def _duracion(self) -> int:
        return _agenda.duracion_en_minutos(
            self.servicio.get("duracion") if self.servicio else None)

    def _reservar(self, que: str) -> Respuesta:
        cita = self.cita
        reservada = self.agenda.reservar(cita.fecha, cita.hora, self._duracion(),
                                         cita.servicio, cita.nombre)
        cita.cerrada = True
        self.esperando = None
        return Respuesta(self.frases.decir(
            "reservada", servicio=que, fecha=self._dicha(cita.fecha),
            hora=fechas.hora_en_palabras(cita.hora), nombre=cita.nombre),
            "cita", aviso=f"Reservada: {cita.resumen()} (id {reservada['id']})",
            tipo_aviso="cita")

    def _si_no_cabe(self, que: str) -> Respuesta | None:
        """None si el hueco pedido cabe. Si no, la respuesta que ofrece otros.

        Se vuelve a preguntar solo lo que toque: el día entero si está
        cerrado, solo la hora si es cosa de la hora. Y los huecos que se
        ofrecen son **cerca de lo que pidió**: a quien quiere la tarde no se le
        ofrece la mañana si hay tarde.
        """
        cita = self.cita
        duracion = self._duracion()
        motivo = self.agenda.por_que_no(cita.fecha, cita.hora, duracion)
        if motivo is None:
            return None

        dicho = self._dicha(cita.fecha)
        dia_dicho = dicho[0].upper() + dicho[1:]

        # Cerrado obliga a cambiar de día. «Ya ha pasado» también, pero solo
        # si no queda nada de hoy: si aún hay huecos más tarde, se ofrecen.
        cambia_dia = motivo == "cerrado" or (
            motivo == "pasado" and not self.agenda.huecos(cita.fecha, duracion))

        if cambia_dia:
            huecos = self.agenda.proximos_huecos(cita.fecha, duracion, por_dia=1)
            dichos = [h.dicho for h in huecos]
            cita.fecha, cita.hora, cita.acotada = None, None, False
            self.esperando = "fecha"
        else:
            pedida = _agenda._minutos(cita.hora)
            huecos = (self.agenda.huecos(cita.fecha, duracion, desde=pedida)
                      or self.agenda.huecos(cita.fecha, duracion))
            dichos = [fechas.hora_en_palabras(h.hora) for h in huecos]
            cita.hora, cita.acotada = None, False
            self.esperando = "hora"

        if not huecos:
            cita.cerrada = True
            self.esperando = None
            return Respuesta(self.frases.decir("sin_huecos"), "cita",
                             aviso=f"Sin huecos para: {cita.resumen()}", tipo_aviso="fallo")

        alternativas = ", ".join(dichos[:-1]) + (" o " if len(dichos) > 1 else "") + dichos[-1]
        clave = {"cerrado": "cerrado", "fuera": "fuera_horario",
                 "ocupado": "ocupado", "pasado": "pasado"}[motivo]
        return Respuesta(self.frases.decir(clave, fecha=dia_dicho, alternativas=alternativas),
                         "cita")

    def _dicha(self, fecha: str) -> str:
        """La fecha como se dice, con el reloj de esta llamada."""
        return fechas.en_palabras(fecha, self.ahora().date())

    def _preguntar_franja(self) -> Respuesta:
        """«A las cinco»: ¿de la mañana o de la tarde? Se propone la plausible.

        Con agenda, si solo una de las dos cae dentro del horario se toma esa
        sin preguntar: nadie quiere que le pregunten si las diez son de la
        noche en una peluquería que cierra a las ocho. Si caben las dos, o no
        hay agenda, se pregunta, proponiendo la más probable: por debajo de
        las ocho, la tarde; a partir de ahí, la mañana.
        """
        cita = self.cita
        h, minutos = int(cita.hora[:2]), cita.hora[3:]
        manana, tarde = f"{h:02d}:{minutos}", f"{h + 12:02d}:{minutos}"

        if self.agenda is not None:
            duracion = self._duracion()
            cabe_m = self.agenda.por_que_no(cita.fecha, manana, duracion) != "fuera"
            cabe_t = self.agenda.por_que_no(cita.fecha, tarde, duracion) != "fuera"
            if cabe_m != cabe_t:
                cita.hora, cita.acotada = (manana if cabe_m else tarde), True
                return self._seguir_cita()

        self._propuesta = tarde if h < 8 else manana
        dicha = fechas.hora_en_palabras(self._propuesta)
        return Respuesta(self.frases.decir(
            "confirma_franja", hora=f"{dicha[0].upper()}{dicha[1:]}"), "cita")

    def _rellenar_con(self, frase: str) -> bool:
        """Mete en la cita lo que traiga esta frase. ¿Ha aportado algo?"""
        cita, puesto = self.cita, False

        if not cita.fecha and (encontrado := fechas.interpretar(frase, self.ahora())) is not None:
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
        h, minutos = int(cita.hora[:2]), cita.hora[3:]
        propuesta = self._propuesta or f"{h + 12:02d}:{minutos}"
        la_otra = f"{h:02d}:{minutos}" if propuesta.startswith(f"{h + 12:02d}") \
            else f"{h + 12:02d}:{minutos}"
        if self.frases.reconoce("si", comparable):
            cita.hora, cita.acotada = propuesta, True
            return self._seguir_cita()
        if self.frases.reconoce("no", comparable):
            # «No» quiere decir la otra. Si la otra es absurda (las cinco de la
            # madrugada), la agenda lo dira y ofrecera huecos; sin agenda se
            # vuelve a preguntar la hora antes que apuntar una de madrugada.
            if self.agenda is not None or int(la_otra[:2]) >= 8:
                cita.hora, cita.acotada = la_otra, True
            else:
                cita.hora, cita.acotada = None, False
            return self._seguir_cita()
        return None

    # -- el turno ------------------------------------------------------------

    def atender(self, frase: str) -> Respuesta:
        """Qué contesta el recepcionista, sabiendo lo que ya se ha dicho."""
        limpia = (frase or "").strip()
        if not limpia:
            return Respuesta(self.frases.decir("no_le_oigo"), "recado")

        respuesta = self._decidir(limpia)
        if respuesta.intencion != "recado":
            self._sin_entender = 0
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
            if ahora_mismo is None:
                # «El de caballero»: no nombra el servicio entero, nombra lo
                # que lo distingue de los otros que se acaban de ofrecer. Se
                # busca solo entre esos, y solo si queda uno.
                ahora_mismo = _entre_ofrecidos(limpia, self._opciones)
            if ahora_mismo is not None:
                self.servicio = ahora_mismo
                return _precio_de(ahora_mismo, self.frases)
            if not (self.frases.reconoce("cita", comparable)
                    or self.frases.reconoce("horario", comparable)
                    or self.frases.reconoce("colgar", comparable)):
                # Han nombrado algo que no está en la tabla. Decirlo es más
                # útil que un «tomo nota» genérico, y sigue sin inventarse
                # ningún precio.
                return Respuesta(
                    self.frases.decir("precio_no_esta"), "precio",
                    aviso=f"Preguntó un precio que no está en tarifas: «{limpia}»",
                    tipo_aviso="fallo")

        if viva and self.esperando == "franja":
            if (hecho := self._confirmar_franja(comparable)) is not None:
                return hecho

        # Se está anulando: lo que llegue es el nombre o cuál de las citas.
        if self.esperando == "anular_nombre":
            if (nombre := _nombre_a_secas(limpia)) is not None:
                self.nombre = nombre
                return self._anular_de(nombre, limpia)
        if self.esperando == "anular_cual" and self._candidatas:
            if (elegida := self._elegir_candidata(limpia)) is not None:
                return self._quitar(elegida)

        # **Anular gana a cita**, y no es un detalle de orden: «anular mi cita
        # del jueves» lleva las dos palabras. Al revés, quien llama para
        # anular cuelga con una cita NUEVA, creyendo que la ha quitado. Dos
        # huecos ocupados y nadie enterado hasta que no aparece.
        if (self.frases.reconoce("anular", comparable)
                or self.frases.reconoce("cambiar", comparable)):
            self._cambiando = self.frases.reconoce("cambiar", comparable)
            return self._anular(limpia)

        # Una frase que trae el dato que se acababa de pedir. Va antes que las
        # intenciones: «el jueves» no lleva la palabra «cita» y aun así lo es.
        if viva and self._rellenar_con(limpia):
            return self._seguir_cita()

        if self.frases.reconoce("cita", comparable):
            self._abrir_cita()
            self._rellenar_con(limpia)
            return self._seguir_cita()

        if self.frases.reconoce("precio", comparable):
            if not conocimiento.tarifas(self.base):
                return Respuesta(self.frases.decir("sin_tarifas"), "precio",
                                 aviso=f"Sin tarifas cargadas. Preguntó: «{limpia}»",
                                 tipo_aviso="fallo")
            respuesta = _responder_precio(limpia, self.base)
            # Si he ofrecido varias, la siguiente frase será cuál de ellas.
            encontrados = conocimiento.buscar(limpia, self.base)
            self._opciones = encontrados if len(encontrados) > 1 else []
            self.esperando = "cual" if self._opciones else None
            return respuesta

        if self.frases.reconoce("horario", comparable):
            return _responder_horario(limpia, self.base)

        if self.frases.reconoce("colgar", comparable):
            return Respuesta(self.frases.decir("despedida"), "recado")

        # Nada que reconocer por reglas. Antes de rendirse, el LLM, si lo hay:
        # devuelve intencion y datos con forma fija, y se atiende como si las
        # reglas lo hubieran entendido. Ni el precio ni la frase los pone el.
        if (entendido := cerebro.entender(limpia, self.base, preguntar=self.preguntar)):
            if (respuesta := self._segun_el_modelo(entendido, limpia)) is not None:
                return respuesta

        # Si hay una cita a medias, se insiste con lo que falta en vez de
        # soltar un «tomo nota» que la abandona.
        if viva:
            return self._seguir_cita()

        # A la tercera seguida sin entender se deja de repetir la misma frase.
        # Un contestador que contesta lo mismo tres veces es un contestador;
        # una persona dice «mire, le tomo el recado y le llamamos».
        self._sin_entender += 1
        clave = "recado_insistente" if self._sin_entender >= 3 else "recado"
        return Respuesta(self.frases.decir(clave), "recado",
                         aviso=f"Recado: «{limpia}»")

    def _segun_el_modelo(self, entendido, limpia: str) -> Respuesta | None:
        """Lo que el modelo entendio, atendido por el mismo camino que las reglas."""
        if entendido.servicio:
            for servicio in conocimiento.tarifas(self.base):
                if servicio["servicio"] == entendido.servicio:
                    self.servicio = servicio
                    if self.cita and not self.cita.cerrada:
                        self.cita.servicio = servicio["servicio"]
        if entendido.nombre:
            self.nombre = entendido.nombre.title()
            if self.cita and not self.cita.cerrada:
                self.cita.nombre = self.nombre

        if entendido.intencion == "precio":
            if self.servicio and entendido.servicio:
                return _precio_de(self.servicio, self.frases)
            return Respuesta(self.frases.decir("precio_no_esta"), "precio",
                             aviso=f"Preguntó un precio que no está en tarifas: «{limpia}»",
                             tipo_aviso="fallo")
        if entendido.intencion == "cita":
            if self.cita is None or self.cita.cerrada:
                self._abrir_cita()
            if entendido.cuando:
                self._rellenar_con(entendido.cuando)
            return self._seguir_cita()
        if entendido.intencion == "horario":
            return _responder_horario(limpia, self.base)
        if entendido.intencion == "despedida":
            return Respuesta(self.frases.decir("despedida"), "recado")
        return None

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


def conversacion_de(negocio) -> Conversacion:
    """Una llamada nueva para un negocio, con agenda si tiene horario escrito."""
    ag = _agenda.Agenda(negocio.ruta.name, negocio.horario) if negocio.horario else None
    return Conversacion(negocio.conocimiento, agenda=ag)


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
