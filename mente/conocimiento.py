"""Lo que el agente sabe del negocio: tarifas y preguntas frecuentes.

## Por qué esto no es un RAG, todavía

La tentación con «que informe de tarifas» es montar embeddings y una base
vectorial. Para una lista de precios es **peor**, y por un motivo concreto:

Un RAG **recupera un trozo** y se lo da al modelo. Si recupera el trozo
equivocado, el agente le canta un precio equivocado a un cliente por teléfono.
Ese error no se ve en las pruebas y se ve en la factura.

Con una lista de veinte servicios, **cabe entera en el prompt**. El modelo lo
ve todo y no hay paso de recuperación que pueda fallar. Menos piezas, menos
maneras de equivocarse, y más barato.

Y hay algo mejor todavía: `buscar()` encuentra el servicio **sin LLM**. Cuando
alguien pregunta «¿cuánto vale la revisión?», el precio sale de la tabla, no
de un modelo generativo. Un número inventado en una tarifa es lo peor que
puede hacer esto.

## Cuándo tocará RAG de verdad

Cuando el conocimiento deje de caber. `cabe_en()` lo dice con números en vez
de a ojo, y ese día la decisión **no se toma por inercia**: un RAG es otra
pieza que mantener y otro sitio donde equivocarse de precio. Se decide por
escrito, con el número de `cabe_en()` delante.

## El formato

`negocios/<negocio>/tarifas.md`, una tabla de Markdown:

    | Servicio | Precio | Duración |
    |---|---|---|
    | Revisión completa | 45 € | 60 min |

`negocios/<negocio>/faq.md`, texto libre. Markdown porque lo tiene que poder editar
quien lleva el negocio, no un programador.
"""

import os
import re
import unicodedata
from pathlib import Path

VARIABLE = "GJALLARHORN_CONOCIMIENTO"

# Un hueco cómodo por debajo de lo que admite cualquier modelo razonable. No es
# un límite técnico: es la raya a partir de la cual meterlo entero deja de ser
# la opción sensata y toca abrir la conversación del RAG.
LIMITE_COMODO = 6000

FILA = re.compile(r"^\|(?!\s*[-: ]+\|)(.+)\|\s*$", re.M)

# Los comentarios de Markdown llevan las instrucciones de la plantilla. NO
# pueden llegar al prompt: el modelo se creeria que "PLANTILLA, esta vacia a
# proposito" es informacion del negocio y se la contaria a un cliente.
COMENTARIO = re.compile(r"<!--.*?-->", re.S)
# Un fichero con solo el titulo esta vacio, aunque tenga bytes.
SOLO_TITULO = re.compile(r"^\s*#+ .*$", re.M)


def carpeta() -> Path:
    valor = os.environ.get(VARIABLE, "").strip()
    # Desde el directorio de trabajo, NUNCA desde `__file__`: esta
    # libreria vive dentro de la aplicacion que la usa, y esta carpeta
    # es de la aplicacion. Con `__file__` acabaria dentro de hugin/.
    return Path(valor).expanduser().resolve() if valor else Path.cwd() / "conocimiento"


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def _leer(nombre: str, base: Path | None = None) -> str:
    """El contenido del fichero **sin los comentarios de la plantilla**."""
    ruta = (base or carpeta()) / nombre
    if not ruta.exists():
        return ""
    return COMENTARIO.sub("", ruta.read_text(encoding="utf-8"))


def _texto_util(texto: str) -> str:
    """Lo que queda quitando titulos, tablas y espacios: el contenido de verdad."""
    resto = SOLO_TITULO.sub("", texto)
    resto = re.sub(r"^\s*\|.*$", "", resto, flags=re.M)
    return resto.strip()


def tarifas(base: Path | None = None) -> list[dict]:
    """Los servicios de `tarifas.md`, como diccionarios.

    Se lee la tabla, no el texto: un precio tiene que poder consultarse exacto,
    no parafrasearse.
    """
    texto = _leer("tarifas.md", base)
    filas = [[c.strip() for c in fila.split("|")] for fila in FILA.findall(texto)]
    if not filas:
        return []
    cabecera = [_sin_tildes(c).replace(" ", "_") for c in filas[0]]
    servicios = []
    for fila in filas[1:]:
        if len(fila) != len(cabecera):
            continue  # una fila torcida se salta; no se adivina qué quería decir
        entrada = dict(zip(cabecera, fila))
        if entrada.get("servicio"):
            servicios.append(entrada)
    return servicios


# Palabras que no dicen nada del servicio ni de la pregunta: se quitan antes
# de comparar. Estan las muletillas del telefono («pues nada, gracias») porque
# si no, «no, gracias» encajaba con la pregunta «¿y si no puedo ir?» por el «no».
VACIAS = {"de", "la", "el", "los", "las", "un", "una", "cuanto", "cuesta",
          "que", "y", "si", "no", "se", "puedo", "puede", "hay", "teneis", "tienen",
          "hace", "falta", "para", "por", "con", "en", "es", "esta", "estais",
          "vale", "precio", "a", "me", "mi", "quiero", "queria", "quisiera",
          "pues", "bueno", "nada", "gracias", "mire", "mira", "oye", "oiga",
          "hola", "buenas", "perdone", "perdon", "entonces", "tambien", "ya",
          "muy", "bien", "ok", "saber", "decir", "decirme", "dime", "digame", "como",
          # Verbos de «¿hacéis…?», «¿tenéis…?»: salen en media FAQ y en casi
          # toda pregunta, así que no distinguen nada y sí despistaban.
          # Verbos de «¿cuanto tarda?». Sin esto, `buscar()` exigia encontrar
          # «tarda» en el nombre del servicio y devolvia vacio: «¿cuanto
          # cuesta un corte?» daba los cuatro cortes y «¿cuanto tarda un
          # corte?» contestaba «no tengo ese servicio», teniendo cuatro.
          "tarda", "tardan", "tardais", "tardaria", "tardarian", "tardando",
          "dura", "duran", "duracion", "tiempo", "listo", "lista", "antelacion",
          "haceis", "hacen", "hacemos", "haces", "podeis", "podemos", "dais",
          "usais", "usan", "atendeis", "atienden", "trabajais", "sois", "soy",
          "lo", "del", "al", "le", "les", "nos", "os", "su", "sus", "tu", "tus",
          "mis", "este", "esto", "ese", "esa", "esos", "esas", "aquel", "aquello",
          "aqui", "alli", "ahi",
          # Palabras de unir frases. Salen en cualquier sitio y no dicen nada,
          # y una de ellas se coló de lo lindo: «hasta» está en «hasta los doce
          # años», así que «pues nada, hasta otra» se llevaba la respuesta de
          # los niños en vez de ser una despedida.
          "hasta", "desde", "entre", "sobre", "cada", "todo", "toda", "todos",
          "otra", "otro", "otros", "mismo", "misma", "mas", "menos", "aunque",
          "porque", "cuando", "mientras", "siempre", "nunca", "solo", "algo",
          "alguna", "alguno", "algun", "cosa", "cosas", "favor", "mejor"}


def _palabras(texto: str) -> set[str]:
    return {p for p in re.findall(r"\w+", _sin_tildes(texto)) if p not in VACIAS}


def palabras_dichas(frase: str, base: Path | None = None) -> set[str]:
    """Las palabras de lo que ha dicho quien llama, traducidas a las de la tabla.

    Los sinónimos son del negocio, en `frases.toml`: «cortarme el pelo» →
    «corte», «reflejos» → «mechas», «para mi hija» → «infantil». Se sustituyen
    los más largos primero, sobre el texto entero, y solo entonces se trocea:
    así «corte de pelo» se convierte en «corte» y no deja «pelo» colgando
    bajándole la cobertura a la búsqueda.
    """
    from hugin.negocio import frases as _frases
    texto = _sin_tildes(frase)
    sinonimos = _frases.cargar(base).sinonimos
    for dicho in sorted(sinonimos, key=len, reverse=True):
        texto = re.sub(rf"\b{re.escape(dicho)}\b", sinonimos[dicho], texto)
    return _palabras(texto)


def vocabulario(base: Path | None = None) -> set[str]:
    """Todas las palabras con las que se nombra algun servicio de la tabla."""
    return set().union(*(_palabras(s["servicio"]) for s in tarifas(base)))


def mencionado(frase: str, base: Path | None = None) -> dict | None:
    """El servicio que se nombra DENTRO de una frase larga, o None.

    `buscar` mide la cobertura sobre lo preguntado, que es lo correcto para
    «¿cuánto vale el tinte?». Pero se rompe con «quiero cita para un tinte el
    jueves a las cinco»: la frase trae diez palabras y el servicio dos, así que
    la cobertura sale baja y no lo encuentra.

    Aquí la cobertura se mide **sobre el servicio**: si el nombre del servicio
    está entero en la frase, es ese. Es la asimetría real —frase larga, nombre
    corto— y no vale para lo otro, por eso son dos funciones.
    """
    dichas = palabras_dichas(frase, base)
    mejor, suyas_mejor = None, 0
    for servicio in tarifas(base):
        suyas = _palabras(servicio["servicio"])
        if suyas and suyas <= dichas and len(suyas) > suyas_mejor:
            # El más específico gana: «corte y tinte» antes que «tinte».
            mejor, suyas_mejor = servicio, len(suyas)
    return mejor


def buscar(consulta: str, base: Path | None = None, tope: int = 4) -> list[dict]:
    """Los servicios que encajan con lo que han preguntado. **Sin LLM.**

    La regla, que no es cosmética: un servicio solo cuenta si lo que se ha
    preguntado coincide en **más de la mitad de sus palabras con contenido**.

    Con una sola palabra compartida no basta, y ese fue un fallo real: «cambio
    de parabrisas» devolvía «Cambio de aceite y filtro, 60 €» porque las dos
    llevan «cambio», y el agente le cantaba a un cliente el precio de un
    servicio que no existe. Ahora la cobertura es 1 de 2 —no pasa de la mitad—
    y devuelve nada, que es la respuesta correcta.

    Primero probé a descartar las palabras que salen en muchos servicios. No
    servía: con cinco servicios, «cambio» sale en dos y no llega a «muchas».
    Complejidad que no arreglaba el caso, así que fuera.

    El precio de esta regla es que «quiero cambiar las ruedas» no encuentra
    «Cambio de neumáticos»: no comparten ninguna palabra. Se prefiere así.
    Callar cuando no se está seguro es barato; cantar el precio de otra cosa,
    no.

    ## La cobertura se mide por los dos lados

    Medirla solo sobre lo preguntado rompía por teléfono, que es donde esto
    vive. Nadie dice «tinte»: dice «buenas, mire, quería saber cuánto vale un
    tinte». Sobre lo preguntado eso es 1 palabra de 4 —no llega a la mitad— y
    el agente contestaba «no tengo ese servicio» teniéndolo en la tabla. Con
    Whisper transcribiendo frases enteras, era el caso normal, no el raro.

    Así que vale con que **cualquiera de los dos lados** pase de la mitad: lo
    preguntado cubierto por el servicio, o el servicio cubierto por lo
    preguntado. Y el caso que originó la regla sigue rechazado, que es lo que
    había que conservar:

        «cambio de parabrisas» vs «Cambio de aceite»
            por lo preguntado: {cambio} de {cambio, parabrisas} = 50 %
            por el servicio:   {cambio} de {cambio, aceite}     = 50 %
            ninguno pasa de la mitad → no se dice nada. Correcto.
    """
    palabras = palabras_dichas(consulta, base)
    if not palabras:
        return []
    puntuados = []
    for servicio in tarifas(base):
        suyas = _palabras(servicio["servicio"])
        comunes = palabras & suyas
        if not comunes:
            continue
        cobertura = max(len(comunes) / len(palabras), len(comunes) / len(suyas))
        if cobertura > 0.5:
            puntuados.append((cobertura, servicio))
    puntuados.sort(key=lambda p: p[0], reverse=True)
    return [servicio for _, servicio in puntuados[:tope]]


def ficheros(base: Path | None = None) -> list[tuple[str, str]]:
    """Los ficheros de conocimiento y cómo se titulan en el prompt.

    Los dos de siempre primero, y detrás cualquier otro `.md` que haya puesto
    el dueño: `servicios.md`, `promociones.md`, lo que sea. Añadir uno es
    añadir conocimiento, sin tocar código y sin dar de alta nada.
    """
    carpeta_ = Path(base) if base else carpeta()
    fijos = [("tarifas.md", "TARIFAS"), ("faq.md", "PREGUNTAS FRECUENTES")]
    if not carpeta_.is_dir():
        return fijos
    otros = sorted(f.name for f in carpeta_.glob("*.md")
                   if f.name not in ("tarifas.md", "faq.md"))
    return fijos + [(n, n[:-3].upper().replace("-", " ")) for n in otros]


def para_prompt(base: Path | None = None) -> str:
    """Todo el conocimiento, tal cual, para meterlo en el prompt del modelo.

    Entero y sin trocear: es justamente lo que evita el paso de recuperación
    que puede equivocarse de precio. Cuando deje de caber —`cabe_en()`— el
    que recupera trozos es `rag.py`.
    """
    partes = []
    for nombre, titulo in ficheros(base):
        texto = _leer(nombre, base).strip()
        # Sin contenido real no se manda la cabecera: un "### TARIFAS" seguido
        # de nada invita al modelo a rellenar el hueco, que es justo lo que no
        # puede hacer con un precio.
        if _hay_algo(nombre, base):
            partes.append(f"### {titulo}\n{texto}")
    return "\n\n".join(partes)


def _hay_algo(nombre: str, base: Path | None = None) -> bool:
    """Si ese fichero tiene contenido de verdad y no solo la plantilla.

    Por fichero y no con una regla comun: en `tarifas.md` lo que cuenta es que
    haya FILAS —la cabecera de la tabla sola no es una tarifa—, y en `faq.md`
    lo que cuenta es que quede texto. Una regla generica se comia las filas
    con datos junto con la cabecera.
    """
    if nombre == "tarifas.md":
        return bool(tarifas(base))
    return bool(_texto_util(_leer(nombre, base)))


def que_falta(base: Path | None = None) -> list[str]:
    """Qué ficheros de conocimiento siguen siendo la plantilla vacía.

    Existe para poder decirlo en voz alta antes de que lo descubra un cliente
    al teléfono.
    """
    return [n for n in ("tarifas.md", "faq.md") if not _hay_algo(n, base)]


def esta_configurado(base: Path | None = None) -> bool:
    """Si hay conocimiento de verdad. Con False, el agente no sabe nada."""
    return not que_falta(base)


def cabe_en(limite: int = LIMITE_COMODO, base: Path | None = None) -> tuple[bool, int]:
    """(¿cabe?, cuánto ocupa). El día que devuelva False, toca hablar de RAG.

    Que sea una función y no un comentario es a propósito: la decisión de
    complicar esto se toma con un número delante, no cuando alguien lo sienta.
    """
    tamano = len(para_prompt(base))
    return tamano <= limite, tamano
