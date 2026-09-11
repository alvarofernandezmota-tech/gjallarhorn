"""Lo que dice el agente y lo que entiende del cliente. Todo editable.

Las tarifas ya se cambiaban sin programar —`tarifas.md`— pero las **palabras**
seguían dentro del código. Eso deja a medias la idea entera: quien lleva el
negocio puede cambiar un precio pero no puede cambiar «Le atiende un asistente
automático» por su forma de saludar, ni enseñarle que en su barrio a las
mechas se las llama «los reflejos».

    negocios/peluqueria/frases.toml

    [dice]        lo que contesta el agente
    [entiende]    lo que puede decir quien llama

Lo que no esté en el fichero usa el valor de aquí, así que un `frases.toml`
con dos líneas es perfectamente válido y una carpeta sin él funciona igual.

## Una plantilla mal escrita no puede tumbar una llamada

Este fichero lo edita alguien que no programa, a las once de la noche, y un
`{fehca}` mal tecleado no puede hacer que el agente cuelgue a un cliente. Así
que `decir()` **nunca levanta**: si la plantilla propia falla, usa la de aquí
y deja un aviso de tipo `fallo` para que se vea al día siguiente.

Es la misma decisión que el aviso de sistema automático en `negocio.py`: lo
que no puede fallar no se deja en manos de que alguien lo escriba bien.
"""

import re
import tomllib
from pathlib import Path

# Lo que dice el agente. Entre llaves van los huecos que se rellenan solos; los
# que admite cada frase estan en HUECOS, y ahi se comprueban.
DICE = {
    "no_le_oigo": "Perdone, no le he oído. ¿Me lo repite?",
    "pide_dia": "Muy bien, una cita{servicio}. ¿Qué día le viene bien?",
    "pide_hora": "Perfecto, {fecha}. ¿A qué hora le viene bien?",
    "confirma_franja": "¿{hora}?",
    "pide_nombre": "¿A nombre de quién se la apunto?",
    "cierra_cita": ("Perfecto. Le apunto la cita{servicio} {fecha} a {hora}, "
                    "a nombre de {nombre}. Se lo confirmamos enseguida."),
    # Con agenda: se reserva de verdad, no se promete que alguien confirmara.
    "reservada": ("Perfecto. Reservada la cita{servicio} {fecha} a {hora}, "
                  "a nombre de {nombre}. Le esperamos."),
    "cerrado": "{fecha} estamos cerrados. Tengo hueco {alternativas}. ¿Le viene bien alguno?",
    "fuera_horario": "A esa hora no estamos abiertos. {fecha} tengo {alternativas}. ¿Le viene bien alguno?",
    "ocupado": "A esa hora ya tengo a alguien. {fecha} me queda {alternativas}. ¿Le viene bien alguno?",
    "pasado": "Esa hora ya ha pasado. Me queda {alternativas}. ¿Le viene bien alguno?",
    "sin_huecos": "No me queda ningún hueco en los próximos días. Le tomo el recado y le llamamos.",
    # «¿Tenéis hueco el jueves?» / «cuando podáis»: se ofrecen los huecos.
    "ofrece_huecos": "{fecha} tengo {alternativas}. ¿Cuál le viene bien?",
    "sin_huecos_dia": "{fecha} no me queda ningún hueco. Tengo {alternativas}. ¿Le viene bien alguno?",
    "primeros_huecos": "Lo más pronto que tengo es {alternativas}. ¿Le viene bien alguno?",
    # «Sí» a varios huecos: ¿cuál?
    "cual_hueco": "¿Cuál de ellos le viene mejor?",
    # Anular. Quien llama para anular NO puede acabar con una cita nueva.
    "anular_nombre": "Claro. ¿A nombre de quién está la cita?",
    "anular_cual": "A ese nombre tengo {citas}. ¿Cuál le anulo?",
    "anular_no_hay": ("No encuentro ninguna cita a nombre de {nombre}. "
                      "Le tomo el recado y lo miramos."),
    "anulada": "Hecho, le anulo la cita{servicio} {fecha} a {hora}.",
    "anulada_y_otra": ("Hecho, le anulo la cita{servicio} {fecha} a {hora}. "
                       "¿Qué día le viene bien la nueva?"),
    "sin_agenda_anular": ("Tomo nota de que quiere anular la cita y se lo "
                          "confirmamos enseguida."),
    # Tercera vez sin entender: se deja de repetir y se toma el recado.
    "recado_insistente": ("Perdone, no acabo de entenderle. Le tomo el recado "
                          "y le devolvemos la llamada en cuanto podamos."),
    # A un «hola, buenas» se contesta invitando a hablar, no tomando nota.
    "digame": "Dígame, ¿en qué puedo ayudarle?",
    # «Por la mañana» tras el dia: la hora, pero ya dentro de esa franja.
    "pide_hora_franja": "Perfecto, {fecha} {franja}. ¿A qué hora?",
    # Nombre dado despues de reservar: se corrige la reserva, no se abre otra.
    "renombrada": "Anotado: la cita queda a nombre de {nombre}.",
    # «¿Cuánto vale?» sin decir el qué, y sin que se haya hablado de nada.
    "cual_servicio": "¿De qué servicio? Así le digo el precio y lo que se tarda.",
    # Tras reservar o anular. Un «no» a esto es la despedida.
    "algo_mas": "¿Le puedo ayudar en algo más?",
    "precio_uno": "{servicio}: {precio}{duracion}.",
    "precio_varios": "Tengo varias opciones: {opciones}. ¿Cuál le interesa?",
    "precio_no_esta": ("No tengo ese servicio en la lista de precios. "
                       "Le tomo el recado y se lo confirmamos."),
    "sin_tarifas": ("Ahora mismo no tengo las tarifas cargadas. "
                    "Le tomo el recado y le devolvemos la llamada."),
    "sin_horario": "No tengo el horario a mano. Le tomo el recado y le llamamos.",
    "recado": "Tomo nota y le devolvemos la llamada en cuanto podamos.",
    "despedida": "Gracias a usted. ¡Hasta luego!",
}

# Los huecos que admite cada frase. Poner uno que no esta en su lista es el
# error tipico al editar, y se caza al cargar en vez de en mitad de la llamada.
HUECOS = {
    "pide_dia": {"servicio"},
    "pide_hora": {"fecha", "servicio"},
    "confirma_franja": {"hora"},
    "cierra_cita": {"servicio", "fecha", "hora", "nombre"},
    "reservada": {"servicio", "fecha", "hora", "nombre"},
    "cerrado": {"fecha", "alternativas"},
    "fuera_horario": {"fecha", "alternativas"},
    "ocupado": {"fecha", "alternativas"},
    "pasado": {"fecha", "alternativas"},   # {fecha} se admite; la de fábrica no la usa
    "anular_cual": {"citas"},
    "ofrece_huecos": {"fecha", "alternativas"},
    "sin_huecos_dia": {"fecha", "alternativas"},
    "primeros_huecos": {"alternativas"},
    "pide_hora_franja": {"fecha", "franja"},
    "renombrada": {"nombre"},
    "anular_no_hay": {"nombre"},
    "anulada": {"servicio", "fecha", "hora"},
    "anulada_y_otra": {"servicio", "fecha", "hora"},
    "precio_uno": {"servicio", "precio", "duracion"},
    "precio_varios": {"opciones"},
}

# Lo que puede decir quien llama. Son trozos de palabra sueltos: se buscan
# enteros, sin tildes y sin distinguir mayusculas.
ENTIENDE = {
    # «vale» a secas NO esta: es la muletilla mas comun del castellano («vale,
    # pues nada, gracias») y se tomaba por «¿cuanto vale?». Solo con «cuanto»
    # o «que» delante es un precio.
    "precio": ["precio", "precios", "cuanto", "cuesta", "cuestan", "cuanto vale",
               "cuanto valen", "que vale", "lo que vale", "tarifa", "tarifas",
               "cobrais", "cobran", "cobra", "sale"],
    # «¿cuanto tarda?» se contesta con el servicio y su duracion, que van juntos.
    "duracion": ["cuanto tarda", "cuanto dura", "cuanto tiempo", "cuanto se tarda",
                 "tardais", "tarda mucho"],
    # Un saludo a secas no es un recado: se le invita a hablar.
    "saludo": ["hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
               "oiga", "diga", "digame", "perdone"],
    "cita": ["cita", "hueco", "reservar", "reserva", "coger", "apuntar",
             "pedir hora", "disponible", "disponibilidad", "libre"],
    # «¿Tenéis hueco el jueves?» pregunta qué hay, no pide una hora: se le
    # dicen los huecos del día en vez de preguntarle «¿a qué hora?».
    "disponibilidad": ["hueco", "huecos", "disponible", "disponibilidad", "libre",
                       "sitio", "teneis algo", "tienes algo", "hay algo", "que horas"],
    # «Cuando podáis»: se ofrecen huecos en vez de insistir con «¿a qué hora?».
    "cualquiera": ["cuando podais", "cuando pueda", "cuando puedas", "cuando tengais",
                   "cuando tengas", "la que tengais", "lo que tengais", "el que tengais",
                   "la que tengas", "lo que tengas", "me da igual", "me es igual",
                   "cualquiera", "cualquier hora", "lo antes posible", "cuanto antes",
                   "primera hora", "a la hora que sea", "cuando sea", "que huecos",
                   "que teneis", "que tienes", "que hay", "lo que haya"],
    "horario": ["horario", "abris", "abren", "cerrais", "cierran", "abierto",
                "cerrado", "hasta que hora", "a que hora"],
    "si": ["si", "sip", "claro", "eso es", "correcto", "exacto", "vale",
           "perfecto", "por la tarde", "de la tarde"],
    "no": ["no", "nop", "que va", "negativo", "por la manana", "de la manana",
           "nada", "nada mas", "eso es todo", "ya esta"],
    "colgar": ["adios", "hasta luego", "gracias", "nada mas", "ya esta",
               "eso es todo", "colgar", "chao"],
    # Anular va ANTES que cita al decidir: «anular mi cita» lleva las dos
    # palabras, y lo que quiere es anular. Al reves se le reserva otra.
    "anular": ["anular", "anula", "cancelar", "cancela", "quitar la cita",
               "quitar mi cita", "no voy a poder ir", "no puedo ir",
               "no podre ir", "me es imposible ir", "dar de baja"],
    "cambiar": ["cambiar la cita", "cambiar mi cita", "cambiar la hora",
                "mover la cita", "cambiarla", "pasarla a otro dia",
                "para otro dia"],
}

# «si» y «no» solo valen al principio de la frase: en mitad de una conversacion
# «no» aparece en «no se» y «no me va bien», y tomarlo por una respuesta es
# peor que ignorarlo.
AL_PRINCIPIO = {"si", "no"}

_CACHE: dict[str, "Frases"] = {}


def _patron(trozos, al_principio: bool) -> re.Pattern:
    alternativas = "|".join(re.escape(t) for t in trozos)
    borde = r"^\W*(?:" if al_principio else r"\b(?:"
    return re.compile(f"{borde}{alternativas})\\b")


class Frases:
    """Las palabras de un negocio: las suyas y las de quien le llama."""

    def __init__(self, dice: dict, entiende: dict):
        self.dice = dice
        self.entiende = {clave: _patron(trozos, clave in AL_PRINCIPIO)
                         for clave, trozos in entiende.items() if trozos}

    def decir(self, clave: str, **datos) -> str:
        """La frase, con sus huecos puestos. No levanta nunca: ver el módulo."""
        plantilla = self.dice.get(clave, DICE[clave])
        try:
            return plantilla.format(**datos).strip()
        except (KeyError, IndexError, ValueError) as error:
            self._quejarse(clave, plantilla, error)
            return DICE[clave].format(**datos).strip()

    def reconoce(self, clave: str, comparable: str) -> bool:
        """¿Lo que ha dicho el cliente suena a esto? `comparable` va sin tildes."""
        patron = self.entiende.get(clave)
        return bool(patron and patron.search(comparable))

    @staticmethod
    def _quejarse(clave, plantilla, error) -> None:
        import avisos
        avisos.registrar("fallo", f"La frase {clave!r} de frases.toml no se pudo "
                                  f"usar ({error}); se ha dicho la de por defecto. "
                                  f"Estaba escrita así: {plantilla!r}")


def revisar(dice: dict) -> list[str]:
    """Los problemas de unas frases propias. Lista vacía si están bien.

    Se usa al arrancar para que un error de edición se vea **antes** de que
    llame nadie, no en el aviso del día siguiente.
    """
    problemas = []
    for clave, plantilla in dice.items():
        if clave not in DICE:
            problemas.append(f"«{clave}» no es ninguna frase del agente. "
                             f"Las que hay: {', '.join(sorted(DICE))}")
            continue
        usados = set(re.findall(r"\{(\w+)", str(plantilla)))
        if sobran := usados - HUECOS.get(clave, set()):
            permitidos = ", ".join(f"{{{h}}}" for h in sorted(HUECOS.get(clave, set())))
            problemas.append(
                f"«{clave}» usa {', '.join('{' + s + '}' for s in sorted(sobran))}, "
                f"que no existe ahí. Puede usar: {permitidos or '(ninguno)'}")
    return problemas


def problemas(base: Path | None = None) -> list[str]:
    """Lo que está mal en el `frases.toml` de un negocio. Vacío si está bien.

    Se llama al arrancar: un `{fehca}` mal tecleado tiene que verse ahí, no
    dentro de tres días en el registro de avisos.
    """
    fichero = Path(base) / "frases.toml" if base else None
    if not fichero or not fichero.exists():
        return []
    try:
        propias = tomllib.loads(fichero.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        return [f"{fichero} no es un TOML válido: {error}"]

    fuera = set(propias) - {"dice", "entiende"}
    encontrados = [f"la sección [{s}] no existe; solo hay [dice] y [entiende]"
                   for s in sorted(fuera)]
    encontrados += revisar(propias.get("dice", {}))
    encontrados += [f"«{i}» no es nada que el agente reconozca; hay: "
                    f"{', '.join(sorted(ENTIENDE))}"
                    for i in sorted(set(propias.get("entiende", {})) - set(ENTIENDE))]
    return encontrados


def cargar(base: Path | None = None) -> Frases:
    """Las frases de un negocio: las suyas encima de las de aquí."""
    clave = str(base or "")
    if clave in _CACHE:
        return _CACHE[clave]

    dice, entiende = dict(DICE), {k: list(v) for k, v in ENTIENDE.items()}
    fichero = Path(base) / "frases.toml" if base else None
    if fichero and fichero.exists():
        propias = tomllib.loads(fichero.read_text(encoding="utf-8"))
        dice.update(propias.get("dice", {}))
        for intencion, trozos in propias.get("entiende", {}).items():
            # Se sustituye, no se suma: quien escribe su lista quiere la suya.
            entiende[intencion] = list(trozos)

    _CACHE[clave] = Frases(dice, entiende)
    return _CACHE[clave]


def olvidar() -> None:
    """Tira la caché. Para las pruebas y para recargar sin reiniciar."""
    _CACHE.clear()
