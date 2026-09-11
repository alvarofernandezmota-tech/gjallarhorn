"""Qué acción toca, a partir de lo que dijiste. Capa 2 del ADR-018.

El ADR deja el cerebro sin decidir: un LLM local o uno por API, y eso se mide
antes de elegir. Mientras tanto **el agente tiene que funcionar**, así que aquí
va un cerebro de reglas: mira cómo empieza la frase y decide.

No pretende ser listo. Pretende tres cosas:

1. **Que el agente sirva hoy**, sin depender de una decisión pendiente.
2. **Que la decisión siga abierta.** Un LLM entra por la misma puerta:
   `decidir(frase) -> (accion, argumentos)`. Cambiar de cerebro no toca ni las
   acciones ni la voz.
3. **Que sea el listón.** Cuando se pruebe un modelo, la pregunta será si acierta
   más que esto. Sin listón, cualquier demo parece buena.

## La regla que más importa

**Lo que no se entiende va al diario, no a la basura.** Si alguien habla y el
agente no sabe qué hacer, lo peor que puede pasar es perder lo que dijo. Una
frase suelta en la entrada del día es recuperable; un «no te he entendido» que
descarta el audio, no.
"""

import re
import unicodedata

# El orden importa: se prueba de arriba abajo y gana la primera. Las más
# específicas van antes, porque «recuérdame comprar pan» también contiene
# «comprar pan» a secas.
#
# Cada regla: (accion, patrón, cómo se sacan los argumentos del texto restante)
REGLAS: list[tuple[str, re.Pattern, str]] = [
    # Preguntas. Van primero: son las únicas que no escriben nada, y
    # confundirlas con una orden significaría apuntar la pregunta en el diario.
    ("que_hay_hoy", re.compile(
        r"^(?:que|qu[eé])\s+(?:tengo|hay|toca|me\s+queda)\b"), ""),
    ("que_hay_hoy", re.compile(r"^(?:c[oó]mo\s+va|resumen|agenda)\b"), ""),
    ("leer_diario", re.compile(
        r"^(?:l[eé]eme|lee|qu[eé]\s+(?:escrib[ií]|puse|apunt[eé]))\b"), ""),

    # Órdenes.
    ("crear_cita", re.compile(
        r"^(?:cita|apunta\s+(?:una\s+)?cita|tengo\s+cita|ponme\s+(?:una\s+)?cita)\b"), "texto"),
    ("crear_tarea", re.compile(
        r"^(?:record[aá]rme|recu[eé]rdame|tarea|tengo\s+que|acu[eé]rdate\s+de|"
        r"ap[uú]ntame\s+(?:la\s+)?tarea)\b"), "texto"),
    ("marcar_habito", re.compile(
        r"^(?:marca|he\s+hecho|hoy\s+he\s+hecho|h[aá]bito)\b"), "nombre"),
    ("apuntar_registro", re.compile(r"^(?:registra|llevo|he\s+tomado)\b"), "que"),
    ("apuntar_en_diario", re.compile(
        r"^(?:apunta|escribe|anota|para\s+el\s+diario|en\s+el\s+diario)\b"), "texto"),
]

# «apunta QUE he ido al gimnasio» → «he ido al gimnasio». El «que» es del verbo,
# no del contenido, y dejarlo escribe «que he ido al gimnasio» en el diario.
ARRANQUE = re.compile(r"^(?:que|de|a|:|,)\s+", re.I)


def _sin_tildes(texto: str) -> str:
    """Para comparar patrones: quien dicta no pone tildes y Whisper a veces tampoco."""
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def decidir(frase: str) -> tuple[str, dict]:
    """(acción, argumentos) para lo que se ha dicho.

    Esta es la firma que tendría que respetar un LLM el día que sustituya a
    esto. Nada de lo de arriba ni de lo de abajo cambia.
    """
    limpia = (frase or "").strip()
    if not limpia:
        raise ValueError("no se ha entendido nada: el audio venía vacío")

    comparable = _sin_tildes(limpia).lower()
    for accion, patron, destino in REGLAS:
        encontrado = patron.match(comparable)
        if not encontrado:
            continue
        # El corte se hace sobre el original, no sobre el comparable: lo que se
        # guarda tiene que llevar sus tildes.
        resto = ARRANQUE.sub("", limpia[encontrado.end():].strip()).strip(" ,.:")
        if not destino:
            return accion, {}
        if not resto:
            # «recuérdame» a secas no es una tarea. Antes que inventarse una
            # vacía, al diario: no se pierde nada.
            return "apuntar_en_diario", {"texto": limpia}
        return accion, {destino: resto}

    # Sin regla que encaje: al diario tal cual. Es la decisión de arriba.
    return "apuntar_en_diario", {"texto": limpia}
