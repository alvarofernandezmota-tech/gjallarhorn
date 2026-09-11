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
    # Una cita sin servicio se reserva con la duración por defecto, y un tinte
    # de hora y media metido en media hora descuadra la tarde entera.
    "pide_servicio": "Muy bien. ¿Para qué servicio se la apunto?",
    # A quien viene siempre a lo mismo se le ofrece, no se le interroga.
    "lo_de_siempre": "Muy bien, {servicio} como siempre. ¿Qué día le viene bien?",
    "no_se_lo_de_siempre": ("Todavía no sé qué suele pedir. ¿Qué servicio quiere?"),
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
    # «¿Eres un robot?», «¿puedo hablar con alguien?»: se dice la verdad.
    "humano": ("Soy un asistente automático. Puedo darle precios, horario y citas. "
               "Si prefiere hablar con una persona, le tomo el recado y le devuelven "
               "la llamada en cuanto puedan."),
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
    "lo_de_siempre": {"servicio"},
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
    # «Lo de siempre», de quien viene cada mes a lo mismo.
    "siempre": ["lo de siempre", "lo mismo de siempre", "como siempre",
                "lo mismo que la ultima vez", "lo mismo que siempre",
                "lo de la ultima vez", "lo habitual", "lo mio de siempre"],
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
    # «¿Cómo?»: se repite lo último que se dijo, sin cambiar nada.
    "repetir": ["repite", "repita", "repitas", "me lo repite", "me lo repites",
                "como dice", "como has dicho", "que has dicho", "que ha dicho",
                "no le he oido", "no te he oido", "no le he entendido",
                "no te he entendido", "otra vez", "no me he enterado"],
    # Quien pregunta si habla con una persona, o pide hablar con una.
    # Sin eñes: se compara sin tildes, y la eñe se queda en ene.
    "humano": ["robot", "maquina", "una persona", "un humano", "hablar con alguien",
               "pasar con", "pasarme con", "pasame con", "me pasas con", "con alguien",
               "con el dueno", "con la duena", "con el encargado", "con la encargada",
               "con alguien", "eres real", "hay alguien", "persona de verdad",
               "una persona real", "con el jefe", "con la jefa"],
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


def _llano(texto: str) -> str:
    """Minúsculas y sin tildes, que es como se compara todo aquí."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(texto).lower())
                   if unicodedata.category(c) != "Mn").strip()


def _patron(trozos, al_principio: bool) -> re.Pattern:
    alternativas = "|".join(re.escape(t) for t in trozos)
    borde = r"^\W*(?:" if al_principio else r"\b(?:"
    return re.compile(f"{borde}{alternativas})\\b")


class Frases:
    """Las palabras de un negocio: las suyas, las de quien le llama, y sus sinónimos."""

    def __init__(self, dice: dict, entiende: dict, sinonimos: dict | None = None):
        self.dice = dice
        self.entiende = {clave: _patron(trozos, clave in AL_PRINCIPIO)
                         for clave, trozos in entiende.items() if trozos}
        # dicho → palabra de la tabla, ya sin tildes: «cortarme» → «corte».
        self.sinonimos = {_llano(dicho): _llano(palabra)
                          for palabra, dichos in (sinonimos or {}).items()
                          for dicho in dichos}

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

    fuera = set(propias) - {"dice", "entiende", "sinonimos"}
    encontrados = [f"la sección [{s}] no existe; hay [dice], [entiende] y [sinonimos]"
                   for s in sorted(fuera)]
    encontrados += [f"en [sinonimos], «{palabra}» tiene que ser una lista de palabras"
                    for palabra, dichos in propias.get("sinonimos", {}).items()
                    if not isinstance(dichos, list)
                    or not all(isinstance(d, str) for d in dichos)]
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
    propias: dict = {}
    if fichero and fichero.exists():
        propias = tomllib.loads(fichero.read_text(encoding="utf-8"))
        dice.update(propias.get("dice", {}))
        for intencion, trozos in propias.get("entiende", {}).items():
            # Se sustituye, no se suma: quien escribe su lista quiere la suya.
            entiende[intencion] = list(trozos)

    _CACHE[clave] = Frases(dice, entiende, propias.get("sinonimos", {}))
    return _CACHE[clave]


def olvidar() -> None:
    """Tira la caché. Para las pruebas y para recargar sin reiniciar."""
    _CACHE.clear()


# Cómo trata el bot a quien llama. No es gramática fina: son las marcas que
# de verdad aparecen en estas frases.
DE_USTED = re.compile(r"\b(usted|le\s|les\s|se\s+l[ao]|su\s|dígame|digame|perdone|"
                      r"viene\s+bien\s+alguno|repite\b)", re.IGNORECASE)
DE_TU = re.compile(r"\b(te\s|tú|tu\s|tus\s|dime|perdona|tienes|quieres|"
                   r"repites|necesitas)\b", re.IGNORECASE)


def tratamiento(texto: str) -> str | None:
    """«tu», «usted» o None si la frase no se moja. Ver `mezcla_de_tratos`."""
    usted, tuteo = len(DE_USTED.findall(texto)), len(DE_TU.findall(texto))
    if usted == tuteo:
        return None
    return "usted" if usted > tuteo else "tu"


def mezcla_de_tratos(dice: dict) -> tuple[str | None, list[str]]:
    """(cómo trata este bot, qué frases se le han quedado del otro lado).

    Un bot que tutea y suelta un «¿le viene bien alguno?» suena a dos
    personas distintas, y pasa solo: las frases que no estén en el
    `frases.toml` del negocio salen de las de fábrica, que tratan de usted.
    Esto lo dice **antes** de que lo oiga un cliente.
    """
    cuenta: dict[str, int] = {"tu": 0, "usted": 0}
    tratos = {}
    for clave, plantilla in dice.items():
        if (trato := tratamiento(str(plantilla))) is not None:
            tratos[clave] = trato
            cuenta[trato] += 1
    if not tratos or cuenta["tu"] == cuenta["usted"]:
        return None, []
    suyo = "tu" if cuenta["tu"] > cuenta["usted"] else "usted"
    return suyo, sorted(clave for clave, trato in tratos.items() if trato != suyo)


def main(argumentos: list[str] | None = None) -> int:
    """`python3 frases.py`: todo lo que va a decir el bot, y cómo trata."""
    import argparse

    import negocio as negocios

    parser = argparse.ArgumentParser(description="Lo que dice tu bot, frase por frase")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--todas", action="store_true",
                        help="también las que usa tal cual de fábrica")
    args = parser.parse_args(argumentos)

    try:
        negocio = negocios.cargar(args.negocio)
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return 1

    for problema in problemas(negocio.conocimiento):
        print(f"⚠️  {problema}")

    suyas = cargar(negocio.conocimiento).dice
    fichero = Path(negocio.conocimiento) / "frases.toml"
    propias = set(tomllib.loads(fichero.read_text(encoding="utf-8")).get("dice", {})) \
        if fichero.exists() else set()

    print(f"{negocio.nombre}: así saluda y así habla\n")
    print(f"  saludo    {negocio.saludo}")
    print(f"  despedida {negocio.despedida}\n")
    for clave, plantilla in suyas.items():
        marca = "·" if clave in propias else " "
        if clave in propias or args.todas:
            print(f" {marca} {clave:20} {plantilla}")
    if not args.todas:
        print(f"\n  (· son suyas; {len(set(suyas) - propias)} más las usa de fábrica, "
              "se ven con --todas)")

    trato, descolgadas = mezcla_de_tratos(suyas)
    if descolgadas:
        como = "de tú" if trato == "tu" else "de usted"
        print(f"\n⚠️  este bot trata {como}, pero estas frases no: "
              f"{', '.join(descolgadas)}")
        print("   Escríbelas en su frases.toml o sonará a dos personas distintas.")
    elif trato:
        print(f"\n✅ trata {'de tú' if trato == 'tu' else 'de usted'} en todo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
