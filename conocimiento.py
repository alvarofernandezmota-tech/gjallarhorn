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
de a ojo. Ese día hay una decisión pendiente que **no se puede tomar sola**:
el ADR-011 de midgaror reserva el RAG para `mimir`, con dos índices —`vida` y
`codigo`— y el argumento explícito de no duplicar el andamiaje. Unas tarifas
de negocio no son ninguno de los dos índices, así que hará falta un ADR que
diga si esto es un tercer índice de mimir o algo aparte. No se decide por
inercia.

## El formato

`conocimiento/tarifas.md`, una tabla de Markdown:

    | Servicio | Precio | Duración |
    |---|---|---|
    | Revisión completa | 45 € | 60 min |

`conocimiento/faq.md`, texto libre. Markdown porque lo tiene que poder editar
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


def carpeta() -> Path:
    valor = os.environ.get(VARIABLE, "").strip()
    return Path(valor).expanduser().resolve() if valor else Path(__file__).resolve().parent / "conocimiento"


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def _leer(nombre: str, base: Path | None = None) -> str:
    ruta = (base or carpeta()) / nombre
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


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


VACIAS = {"de", "la", "el", "los", "las", "un", "una", "cuanto", "cuesta",
          "vale", "precio", "que", "por", "para", "y", "a", "me", "mi", "quiero"}


def _palabras(texto: str) -> set[str]:
    return {p for p in re.findall(r"\w+", _sin_tildes(texto)) if p not in VACIAS}


def buscar(consulta: str, base: Path | None = None, tope: int = 3) -> list[dict]:
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
    """
    palabras = _palabras(consulta)
    if not palabras:
        return []
    puntuados = []
    for servicio in tarifas(base):
        comunes = palabras & _palabras(servicio["servicio"])
        cobertura = len(comunes) / len(palabras)
        if cobertura > 0.5:
            puntuados.append((cobertura, servicio))
    puntuados.sort(key=lambda p: p[0], reverse=True)
    return [servicio for _, servicio in puntuados[:tope]]


def para_prompt(base: Path | None = None) -> str:
    """Todo el conocimiento, tal cual, para meterlo en el prompt del modelo.

    Entero y sin trocear: es justamente lo que evita el paso de recuperación
    que puede equivocarse de precio.
    """
    partes = []
    for nombre, titulo in (("tarifas.md", "TARIFAS"), ("faq.md", "PREGUNTAS FRECUENTES")):
        texto = _leer(nombre, base).strip()
        if texto:
            partes.append(f"### {titulo}\n{texto}")
    return "\n\n".join(partes)


def cabe_en(limite: int = LIMITE_COMODO, base: Path | None = None) -> tuple[bool, int]:
    """(¿cabe?, cuánto ocupa). El día que devuelva False, toca hablar de RAG.

    Que sea una función y no un comentario es a propósito: la decisión de
    complicar esto se toma con un número delante, no cuando alguien lo sienta.
    """
    tamano = len(para_prompt(base))
    return tamano <= limite, tamano
