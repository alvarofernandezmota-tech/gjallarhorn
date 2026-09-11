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
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

import agenda as _agenda
import avisos
import cerebro
import conocimiento
import fechas
import frases as _frases
import negocio as negocios
import rag
import voz

@dataclass(frozen=True)
class Respuesta:
    """Lo que el agente dice, y lo que hay que apuntar de la llamada."""

    texto: str          # lo que se le contesta a quien llama
    intencion: str      # precio | cita | horario | recado
    aviso: str | None = None   # qué registrar en avisos.py, si procede
    tipo_aviso: str = "llamada"
    cuelga: bool = False       # con esta frase se termina la llamada


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


def _entre_ofrecidos(frase: str, ofrecidos: list[dict], base: Path | None = None) -> dict | None:
    """Cuál de los servicios ofrecidos nombra la frase, por sus palabras.

    Entre «Corte de caballero» y «Corte de señora», «el de caballero» solo
    comparte una palabra con el primero: basta. La búsqueda general exige
    cubrir más de la mitad del nombre y aquí fallaba —«caballero» es 1 de
    2— justo cuando el cliente acaba de elegir.
    """
    dichas = conocimiento.palabras_dichas(frase, base)
    if not dichas or not ofrecidos:
        return None
    candidatos = [s for s in ofrecidos if dichas & conocimiento._palabras(s["servicio"])]
    if len(candidatos) != 1:
        return None
    # La palabra tiene que distinguirlo, no ser la comun a todos («corte»).
    comunes = set.intersection(*(conocimiento._palabras(s["servicio"]) for s in ofrecidos))
    return candidatos[0] if dichas & conocimiento._palabras(candidatos[0]["servicio"]) - comunes else None


def _precio_de(servicio: dict, frases) -> Respuesta:
    """Un servicio y su precio, dicho igual se llegue por donde se llegue.

    La duración, como se dice: «una hora y media», no «90 min». Si lo escrito
    en la tabla no se entiende, se lee tal cual.
    """
    escrita = servicio.get("duracion")
    dicha = fechas.duracion_en_palabras(escrita)
    duracion = f", {dicha}" if dicha else f", unos {escrita}" if escrita else ""
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
# devolverle el nombre sin tildes a quien acaba de decirlo. El grupo «yo»
# distingue presentarse («soy Marta») de dar el nombre de otra persona («a
# nombre de Lucía»): lo primero dice quién llama; lo segundo, solo quién viene.
# La segunda palabra del nombre no puede ser una conjunción: «Marta y quería»
# no es «Marta Y».
NOMBRE = re.compile(
    r"\b(?:(?P<yo>me\s+llamo|mi\s+nombre\s+es|soy)|a\s+nombre\s+de|de\s+parte\s+de|"
    r"para\s+(?:el\s+se[nñ]or|la\s+se[nñ]ora)\s+de|(?:la\s+)?cita\s+de)\s+"
    r"(?P<nombre>[^\W\d_]+(?:\s+(?!(?:y|e|o|u|que|para|de|del|la|el|con|por|pero|quiero|"
    r"queria|quería|me|mi|a|un|una)\b)[^\W\d_]+)?)", re.IGNORECASE | re.UNICODE)

# Palabras que nunca son un nombre, por mucho que vayan detrás de «soy» o de
# «la cita de»: «la cita de mañana» no es de nadie que se llame Mañana.
NO_ES_NOMBRE = {"un", "una", "el", "la", "los", "las", "mi", "su", "para",
                "que", "de", "del", "por", "cliente", "nueva", "nuevo", "yo",
                "hoy", "manana", "pasado", "esta", "este", "ese", "esa",
                "las", "los", *fechas.DIAS}

# Preguntas en condicional: «¿y si no puedo ir?» no es «no puedo ir». Lo
# primero se contesta con la FAQ; lo segundo anula la cita.
HIPOTETICA = re.compile(r"^\W*(?:y\s+)?(?:si|cuando)\s+")

# «¿Cómo?», «¿qué?», «¿mande?»: una sola palabra que pide que se repita. Solo
# a secas: «¿cómo anulo la cita?» es una pregunta, no un «¿cómo?».
REPITE_A_SECAS = {"como", "que", "eh", "perdon", "perdona", "perdone", "mande", "diga"}

# Lo que se dice al preguntar un precio sin nombrar el qué: «¿y cuánto me va
# a costar?». Si tras quitar esto no queda palabra, no se ha nombrado ningún
# servicio, y entonces vale el del que se venía hablando.
RELLENO = {"costar", "costaria", "costara", "va", "valer", "valdria", "valen",
           "cobrais", "cobran", "cobra", "cobrar", "sale", "saldria", "precios",
           "tarifa", "tarifas", "tarda", "tardan", "tardais", "tardaria", "dura",
           "duran", "tiempo", "mucho", "eso", "esto", "ese", "esa", "lleva",
           "seria", "ser", "total", "todo", "podria", "puedes", "hora", "horas",
           "minutos", "aproximadamente", "mas", "o", "menos", "entonces", "al",
           "final", "aqui", "ahi", "cuestan", "cuanto"}

def _ambigua(hora: str, acotada: bool) -> bool:
    """¿«Las cinco» podrían ser las 17:00 y nadie lo ha dicho?

    A partir de las 12 no hay duda: «las 17» son las 17. La ambigüedad solo
    existe por debajo, y es la que manda a alguien a la puerta de madrugada.
    """
    return not acotada and int(hora[:2]) < 12


def _nombre_en(frase: str, base: Path | None = None) -> tuple[str, bool] | None:
    """(nombre, ¿se ha presentado?) si se ha dado con todas las letras.

    «La cita de tinte» no es de nadie que se llame Tinte: lo que nombra un
    servicio de la tabla no es un nombre.
    """
    if (m := NOMBRE.search(frase)) is None:
        return None
    nombre = " ".join(m.group("nombre").split())
    primera = _sin_tildes(nombre.split()[0])
    if primera in NO_ES_NOMBRE or primera in conocimiento.vocabulario(base):
        return None
    return nombre.title(), m.group("yo") is not None


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
    franja: str | None = None     # «por la tarde», dicho antes que la hora
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
        self.nombre: str | None = None        # a nombre de quién va lo que se pida
        self.presentado: str | None = None    # cómo se ha presentado quien llama
        self.esperando: str | None = None     # qué se acaba de preguntar
        self._ultima_reserva: int | None = None   # por si luego corrige el nombre
        self._propuesta: str | None = None    # la hora propuesta al preguntar la franja
        self._candidatas: list[dict] = []     # citas entre las que hay que elegir al anular
        self._ofrecidos: list = []            # huecos ofrecidos; «sí» o «el primero» elige uno
        self.recuerdos = None                 # memoria.Ficha de quien llama, si se le conoce
        self.reservadas: list[dict] = []      # lo que se ha cerrado en esta llamada
        self.anulaciones = 0                  # y lo que se ha quitado
        self._opciones: list[dict] = []       # servicios ofrecidos en «¿cuál le interesa?»
        self._cambiando = False               # anular para poner otra, no solo anular
        self._sin_entender = 0                # seguidas; a la tercera se toma el recado
        self.turnos: list[tuple[str, str]] = []

    def recordar(self, ficha) -> None:
        """La ficha de quien llama, de una llamada anterior.

        Se usa para dos cosas y ninguna más: saber su nombre sin preguntarlo
        y poder ofrecerle lo de siempre. No decide nada por él.
        """
        self.recuerdos = ficha
        if ficha is not None and ficha.nombre:
            self.nombre = ficha.nombre

    def _servicio_habitual(self) -> dict | None:
        """El servicio que suele pedir, buscado en la tabla de hoy.

        Se busca por el nombre guardado: si el dueño quitó ese servicio de
        `tarifas.md`, deja de existir y no se le ofrece. La tabla manda,
        también sobre lo que recuerda la ficha.
        """
        if self.recuerdos is None or not self.recuerdos.habitual:
            return None
        for servicio in conocimiento.tarifas(self.base):
            if servicio["servicio"] == self.recuerdos.habitual:
                return servicio
        return None

    # -- lo que se recuerda de cada frase, se pregunte lo que se pregunte ----

    def _recordar(self, frase: str) -> tuple[dict | None, str | None]:
        """Guarda lo que aporte esta frase. Devuelve (servicio, nombre) que nombra AHORA.

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
        nombre = None
        if (dado := _nombre_en(frase, self.base)) is not None:
            nombre, se_presenta = dado
            if se_presenta:
                self.presentado = nombre
            if self.cita and not self.cita.cerrada:
                self.cita.nombre = nombre
            # Con una cita ya cerrada, «a nombre de Lucía» corrige esa cita; no
            # cambia quién llama, que es lo que se recuerda del número.
            if se_presenta or self.nombre is None or (self.cita and not self.cita.cerrada):
                self.nombre = nombre
        return servicio, nombre

    # -- la cita, turno a turno ---------------------------------------------

    def _abrir_cita(self) -> Cita:
        self.cita = Cita(servicio=self.servicio["servicio"] if self.servicio else None,
                         nombre=self.nombre)
        self._ofrecidos = []
        return self.cita

    @staticmethod
    def _enumerar(dichos: list[str]) -> str:
        """«A, B o C»: como se lee una lista en voz alta."""
        return ", ".join(dichos[:-1]) + (" o " if len(dichos) > 1 else "") + dichos[-1]

    def _ofrecer_huecos(self) -> Respuesta:
        """Los huecos del día que ha dicho, en la franja que ha dicho si la ha dicho.

        «¿Tenéis hueco el jueves por la tarde?» se contesta con los huecos de
        la tarde del jueves, no con «¿a qué hora le viene bien?». Si ese día
        no queda nada, se ofrecen los primeros de los días siguientes.
        """
        cita, duracion = self.cita, self._duracion()
        # Si no ha dicho franja pero siempre viene a la misma, se empieza por
        # ahí. Es una preferencia, no una regla: si ahí no queda nada, se le
        # ofrece lo que haya.
        if cita.franja is None and self.recuerdos is not None:
            cita.franja = self.recuerdos.franja
        desde = hasta = None
        if cita.franja in ("tarde", "noche"):
            desde = 14 * 60
        elif cita.franja == "manana":
            hasta = 14 * 60
        elif cita.franja == "mediodia":
            desde, hasta = 12 * 60, 16 * 60
        huecos = (self.agenda.huecos(cita.fecha, duracion, desde=desde, hasta=hasta)
                  or self.agenda.huecos(cita.fecha, duracion))
        dicho = self._dicha(cita.fecha)
        dia = dicho[0].upper() + dicho[1:]
        if huecos:
            self._ofrecidos, self.esperando = huecos, "hora"
            return Respuesta(self.frases.decir(
                "ofrece_huecos", fecha=dia,
                alternativas=self._enumerar([fechas.hora_en_palabras(h.hora) for h in huecos])),
                "cita")
        siguiente = (date.fromisoformat(cita.fecha) + timedelta(days=1)).isoformat()
        proximos = self.agenda.proximos_huecos(siguiente, duracion, por_dia=1)
        if not proximos:
            return self._sin_huecos()
        self._ofrecidos, self.esperando = proximos, "fecha"
        cita.fecha, cita.franja = None, None
        return Respuesta(self.frases.decir(
            "sin_huecos_dia", fecha=dia,
            alternativas=self._enumerar([h.dicho for h in proximos])), "cita")

    def _primeros_huecos(self) -> Respuesta:
        """«Cuando podáis», sin día: lo más pronto que hay, un hueco por día."""
        proximos = self.agenda.proximos_huecos(self.ahora().strftime("%Y-%m-%d"),
                                               self._duracion(), por_dia=1)
        if not proximos:
            return self._sin_huecos()
        self._ofrecidos, self.esperando = proximos, "fecha"
        return Respuesta(self.frases.decir(
            "primeros_huecos", alternativas=self._enumerar([h.dicho for h in proximos])), "cita")

    def _sin_huecos(self) -> Respuesta:
        self.cita.cerrada = True
        self.esperando = None
        return Respuesta(self.frases.decir("sin_huecos"), "cita",
                         aviso=f"Sin huecos para: {self.cita.resumen()}", tipo_aviso="fallo")

    def _hueco_elegido(self, comparable: str) -> "_agenda.Hueco | None":
        """Cuál de los huecos ofrecidos ha elegido: «sí» al único, «el primero», «el último»."""
        if not self._ofrecidos:
            return None
        # «Sí» al único hueco lo coge; «sí, a las seis» dice otra hora y esa manda.
        corta = len(comparable.split()) <= 4 and fechas.hora_suelta(comparable) is None
        if corta and self.frases.reconoce("si", comparable) and len(self._ofrecidos) == 1:
            return self._ofrecidos[0]
        if re.search(r"\b(?:el|la)\s+primer[oa]\b|\bprimer[oa]\b", comparable):
            return self._ofrecidos[0]
        if re.search(r"\b(?:el|la)\s+ultim[oa]\b", comparable):
            return self._ofrecidos[-1]
        return None

    def _coger_hueco(self, hueco) -> Respuesta:
        cita = self.cita
        cita.fecha, cita.hora, cita.acotada = hueco.fecha, hueco.hora, True
        self._ofrecidos = []
        return self._seguir_cita()

    def _seguir_cita(self) -> Respuesta:
        """La siguiente pregunta, o el cierre si ya no falta nada."""
        cita = self.cita
        que = f" de {cita.servicio.lower()}" if cita.servicio else ""
        self.esperando = falta = cita.falta()

        if falta == "fecha":
            return Respuesta(self.frases.decir("pide_dia", servicio=que), "cita")
        if falta == "hora":
            if cita.franja:
                return Respuesta(self.frases.decir(
                    "pide_hora_franja", fecha=self._dicha(cita.fecha),
                    franja=fechas.FRANJAS_DICHAS[cita.franja]), "cita")
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
            self.reservadas.append({"servicio": cita.servicio, "hora": cita.hora,
                                    "fecha": cita.fecha})
            return Respuesta(self._y_algo_mas(self.frases.decir(
                "cierra_cita", servicio=que, fecha=self._dicha(cita.fecha),
                hora=fechas.hora_en_palabras(cita.hora), nombre=cita.nombre)), "cita")
        if (no_cabe := self._si_no_cabe(que)) is not None:
            # Entre la comprobacion de antes y ahora ha podido entrar otra
            # llamada. Se vuelve a mirar; la agenda lo mira otra vez al reservar.
            return no_cabe
        return self._reservar(que)

    # -- anular --------------------------------------------------------------

    def _anular(self, frase: str, nombre: str | None = None) -> Respuesta:
        """Quitar una cita. Sin agenda se toma nota; con agenda se quita.

        El nombre que trae la frase («la cita de Lucía») manda sobre el que
        se recordaba: quien llama puede estar anulando la de otra persona.
        """
        if self.agenda is None:
            self.esperando = None
            return Respuesta(self.frases.decir("sin_agenda_anular"), "cita",
                             aviso=f"Quiere anular una cita: «{frase}»", tipo_aviso="cita")
        nombre = nombre or self.nombre
        if not nombre:
            self.esperando = "anular_nombre"
            return Respuesta(self.frases.decir("anular_nombre"), "cita")
        return self._anular_de(nombre, frase)

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
        self.anulaciones += 1
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

        return Respuesta(self._y_algo_mas(self.frases.decir(
            "anulada", servicio=que, fecha=self._dicha(quitada["fecha"]),
            hora=fechas.hora_en_palabras(quitada["hora"]))), "cita",
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
        self._ultima_reserva = reservada["id"]
        self.reservadas.append(reservada)
        return Respuesta(self._y_algo_mas(self.frases.decir(
            "reservada", servicio=que, fecha=self._dicha(cita.fecha),
            hora=fechas.hora_en_palabras(cita.hora), nombre=cita.nombre)),
            "cita", aviso=f"Reservada: {cita.resumen()} (id {reservada['id']})",
            tipo_aviso="cita")

    def _y_algo_mas(self, texto: str) -> str:
        """Cierra un asunto y pregunta si hay otro. Un «no» aquí es la despedida.

        Sin la pregunta, tras «reservada, le esperamos» el teléfono se queda
        escuchando en silencio y quien llama no sabe si tiene que colgar o
        si se ha cortado. Se puede quitar dejando `algo_mas` vacío.
        """
        self.esperando = "algo_mas"
        return f"{texto} {self.frases.decir('algo_mas')}".strip()

    def _renombrar(self, nombre: str) -> Respuesta | None:
        """«A nombre de Lucía» después de reservar: se corrige, no se abre otra."""
        if self.agenda is not None:
            if self._ultima_reserva is None \
                    or self.agenda.renombrar(self._ultima_reserva, nombre) is None:
                return None
        self.cita.nombre = nombre
        return Respuesta(self.frases.decir("renombrada", nombre=nombre), "cita",
                         aviso=f"La cita {self._ultima_reserva or ''} pasa a nombre de "
                               f"{nombre}".replace("  ", " "), tipo_aviso="cita")

    def _con_lo_pendiente(self, respuesta: Respuesta) -> Respuesta:
        """Una pregunta suelta en mitad de una cita: se contesta y se retoma.

        «¿Aceptáis tarjeta?» cuando se estaba preguntando la hora se contesta
        y, en la misma frase, se vuelve a preguntar la hora. Si no, la cita
        se queda a medias y quien llama cree que ya está.
        """
        if self.cita is None or self.cita.cerrada or self.esperando == "cual":
            return respuesta
        siguiente = self._seguir_cita()
        return replace(respuesta, texto=f"{respuesta.texto} {siguiente.texto}")

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
            return self._sin_huecos()

        self._ofrecidos = huecos
        clave = {"cerrado": "cerrado", "fuera": "fuera_horario",
                 "ocupado": "ocupado", "pasado": "pasado"}[motivo]
        return Respuesta(self.frases.decir(clave, fecha=dia_dicho,
                                           alternativas=self._enumerar(dichos)), "cita")

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

        # Lo ofrecido completa lo que falte: si ofrecí «el martes a las diez» y
        # dice «el martes», son las diez; si ofrecí las cinco de la tarde y dice
        # «las cinco», son las de la tarde y no se vuelve a preguntar.
        if puesto and self._ofrecidos:
            del_dia = [h for h in self._ofrecidos if h.fecha == cita.fecha]
            if cita.hora and not cita.acotada:
                horas = {h.hora for h in del_dia}
                for candidata in (cita.hora, fechas.acotar(cita.hora, "tarde")):
                    if candidata in horas:
                        cita.hora, cita.acotada = candidata, True
                        break
            elif not cita.hora and len(del_dia) == 1:
                cita.hora, cita.acotada = del_dia[0].hora, True
            if cita.hora:
                self._ofrecidos = []

        # «Por la tarde» se recuerda aunque venga sin hora: cuando llegue «a
        # las cinco», ya son las cinco de la tarde y no hay que preguntarlo.
        if (franja := fechas.franja_en(frase)) is not None and not cita.acotada:
            cita.franja = franja
            puesto = puesto or self.esperando in ("hora", "fecha")
        if cita.hora and not cita.acotada and cita.franja:
            cita.hora, cita.acotada = fechas.acotar(cita.hora, cita.franja), True

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
        if respuesta.intencion != "recado" or respuesta.cuelga:
            self._sin_entender = 0
        self.turnos.append((limpia, respuesta.texto))
        return respuesta

    def _decidir(self, limpia: str) -> Respuesta:
        comparable = _sin_tildes(limpia)
        ahora_mismo, nombre_dado = self._recordar(limpia)
        viva = self.cita is not None and not self.cita.cerrada

        # «¿Cómo?», «¿me lo repite?»: lo último que se dijo, tal cual, sin
        # tocar nada de lo que se estaba haciendo.
        if (self.frases.reconoce("repetir", comparable) and len(comparable.split()) <= 7) \
                or comparable.strip("¿?¡!., ") in REPITE_A_SECAS:
            ultimo = self.turnos[-1][1] if self.turnos else self.frases.decir("digame")
            return Respuesta(ultimo, "repetir")

        # «¿Algo más?» → «no, gracias» es la despedida; «sí» es «dígame».
        # Cualquier otra cosa se atiende como lo que sea.
        if self.esperando == "algo_mas":
            self.esperando = None
            corta = len(comparable.split()) <= 4
            if self.frases.reconoce("colgar", comparable) \
                    or (corta and self.frases.reconoce("no", comparable)):
                return self._despedida()
            if corta and self.frases.reconoce("si", comparable):
                return Respuesta(self.frases.decir("digame"), "saludo")

        # Nombre dado después de reservar: corrige la reserva, no abre otra.
        if nombre_dado and self.cita is not None and self.cita.cerrada \
                and not self._pide_otra_cosa(comparable):
            if (hecho := self._renombrar(nombre_dado)) is not None:
                return hecho

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
                ahora_mismo = _entre_ofrecidos(limpia, self._opciones, self.base)
            if ahora_mismo is not None:
                self.servicio = ahora_mismo
                return self._con_lo_pendiente(_precio_de(ahora_mismo, self.frases))
            if not conocimiento._palabras(limpia) - RELLENO:
                # «¿Y cuánto tarda?» sin decir cuál: se vuelve a preguntar cuál.
                self.esperando = "cual"
                if self._opciones:
                    opciones = "; ".join(f"{s['servicio']} {s['precio']}" for s in self._opciones)
                    return Respuesta(self.frases.decir("precio_varios", opciones=opciones), "precio")
                return Respuesta(self.frases.decir("cual_servicio"), "precio")
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
                or self.frases.reconoce("cambiar", comparable)) \
                and not HIPOTETICA.match(comparable):
            self._cambiando = self.frases.reconoce("cambiar", comparable)
            return self._anular(limpia, nombre_dado)

        # He ofrecido huecos y me dicen cuál: «sí» al único, «el primero»…
        if viva and self.esperando in ("hora", "fecha") and self._ofrecidos:
            if (hueco := self._hueco_elegido(comparable)) is not None:
                return self._coger_hueco(hueco)
            if len(comparable.split()) <= 4 and self.frases.reconoce("si", comparable):
                return Respuesta(self.frases.decir("cual_hueco"), "cita")

        # «Lo de siempre»: lo que pidió las otras veces, sin hacerle repetirlo.
        # Salvo que nombre otra cosa en la misma frase, que entonces manda esa:
        # «como siempre, pero esta vez unas mechas» son mechas.
        if self.frases.reconoce("siempre", comparable) and ahora_mismo is None:
            habitual = self._servicio_habitual()
            if habitual is not None:
                self.servicio = habitual
                if not viva:
                    self._abrir_cita()
                self.cita.servicio = habitual["servicio"]
                self._rellenar_con(limpia)
                if self.cita.fecha:
                    return self._seguir_cita()
                self.esperando = "fecha"
                return Respuesta(self.frases.decir(
                    "lo_de_siempre", servicio=habitual["servicio"].lower()), "cita")
            if not self._pide_otra_cosa(comparable):
                return Respuesta(self.frases.decir("no_se_lo_de_siempre"), "cita")

        # «Cuando podáis», «el que tengáis»: se ofrecen huecos en vez de
        # insistir con «¿a qué hora?». Solo con agenda: sin ella no hay huecos.
        if self.agenda is not None and self.frases.reconoce("cualquiera", comparable) \
                and (viva or self.frases.reconoce("cita", comparable)):
            if not viva:
                self._abrir_cita()
            self._rellenar_con(limpia)
            if self.cita.fecha and not self.cita.hora:
                return self._ofrecer_huecos()
            if not self.cita.fecha:
                return self._primeros_huecos()
            return self._seguir_cita()

        # Una frase que trae el dato que se acababa de pedir. Va antes que las
        # intenciones: «el jueves» no lleva la palabra «cita» y aun así lo es.
        if viva and self._rellenar_con(limpia):
            return self._seguir_cita()

        if self.frases.reconoce("cita", comparable) \
                or self.frases.reconoce("disponibilidad", comparable):
            self._abrir_cita()
            self._rellenar_con(limpia)
            # «¿Tenéis hueco el jueves?» pregunta qué hay: se le dice, en vez
            # de preguntarle a él la hora.
            if self.agenda is not None and self.cita.fecha and not self.cita.hora \
                    and self.frases.reconoce("disponibilidad", comparable):
                return self._ofrecer_huecos()
            return self._seguir_cita()

        if self.frases.reconoce("precio", comparable) \
                or self.frases.reconoce("duracion", comparable):
            if not conocimiento.tarifas(self.base):
                return Respuesta(self.frases.decir("sin_tarifas"), "precio",
                                 aviso=f"Sin tarifas cargadas. Preguntó: «{limpia}»",
                                 tipo_aviso="fallo")
            return self._con_lo_pendiente(self._precio(limpia))

        if self.frases.reconoce("horario", comparable):
            return self._con_lo_pendiente(_responder_horario(limpia, self.base))

        # Lo demás que esté escrito en los .md del negocio: tarjeta, dónde, si
        # hace falta cita, el aparcamiento… Lo busca `rag.py` y se contesta con
        # el texto del dueño, tal cual. Si no hay nada claro, calla y se toma
        # el recado: contestar otra pregunta es peor que no contestar.
        if (pasaje := rag.responder(limpia, self.base)) is not None:
            return self._con_lo_pendiente(Respuesta(
                pasaje.dicho, "faq",
                aviso=f"Contestado de {pasaje.fuente}: «{limpia}»", tipo_aviso="llamada"))

        if self.frases.reconoce("colgar", comparable):
            return self._despedida()

        # «Hola, buenas» a secas: se le invita a hablar, no se toma nota. Con
        # una cita a medias se repite lo que faltaba.
        if self.frases.reconoce("saludo", comparable) and len(comparable.split()) <= 4:
            if viva:
                return self._seguir_cita()
            return Respuesta(self.frases.decir("digame"), "saludo")

        # «¿Eres un robot?», «¿puedo hablar con alguien?»: se dice lo que es y
        # se toma el recado. Nunca se hace pasar por una persona.
        if self.frases.reconoce("humano", comparable):
            return Respuesta(self.frases.decir("humano"), "recado",
                             aviso=f"Pide hablar con una persona: «{limpia}»")

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
                         aviso=f"Recado: «{limpia}»", cuelga=clave == "recado_insistente")

    def _despedida(self) -> Respuesta:
        return Respuesta(self.frases.decir("despedida"), "recado", cuelga=True)

    def _pide_otra_cosa(self, comparable: str) -> bool:
        """¿La frase trae, además, alguna de las peticiones que se atienden?"""
        return any(self.frases.reconoce(clave, comparable)
                   for clave in ("cita", "precio", "duracion", "horario", "anular", "cambiar"))

    def _precio(self, limpia: str) -> Respuesta:
        """El precio de lo que se nombra AHORA; si no se nombra nada, el de antes.

        La regla sigue siendo que el precio sale de la tabla o no sale. Lo que
        cambia es qué se hace cuando la frase no nombra ningún servicio:

        - «¿y cuánto me va a costar?» tras hablar del tinte → el del tinte.
        - «¿cuánto vale?» sin haber hablado de nada → se pregunta el qué.
        - «¿cuánto vale un masaje?» → no está, y se dice. Aquí NO vale el de
          antes: nombra otra cosa, y el precio de otra cosa no se canta.
        """
        encontrados = conocimiento.buscar(limpia, self.base)
        if encontrados:
            # Si he ofrecido varias, la siguiente frase será cuál de ellas.
            self._opciones = encontrados if len(encontrados) > 1 else []
            self.esperando = "cual" if self._opciones else None
            if len(encontrados) == 1:
                self.servicio = encontrados[0]
            return _responder_precio(limpia, self.base)
        if conocimiento._palabras(limpia) - RELLENO:
            return Respuesta(
                self.frases.decir("precio_no_esta"), "precio",
                aviso=f"Preguntó un precio que no está en tarifas: «{limpia}»",
                tipo_aviso="fallo")
        if self.servicio is not None:
            return _precio_de(self.servicio, self.frases)
        self._opciones, self.esperando = [], "cual"
        return Respuesta(self.frases.decir("cual_servicio"), "precio")

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
            return self._despedida()
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
