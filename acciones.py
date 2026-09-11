"""Qué sabe hacer el agente. La capa 1 del ADR-018 de midgaror.

Un catálogo de acciones sobre el diario. Cada una **envuelve una función de
midgaror que ya existe y ya está probada** —las mismas que llama bifrost desde
Telegram—, así que aquí no se reimplementa nada ni se escribe un JSON a mano.
Es la regla del ADR-009 llevada al resto de los modelos: un solo sitio por el
que se escribe cada cosa.

Esta capa no sabe nada de voz ni de LLM. Se puede construir y probar entera
sin haber decidido el cerebro ni haber resuelto la telefonía, que es
justamente por lo que se empieza por aquí.

Cómo se usa desde arriba:

    catalogo()                      # las herramientas, en formato de LLM
    ejecutar("crear_tarea", texto="llamar al dentista el jueves")

`ejecutar` devuelve **una frase corta**, no un objeto: lo que sale de aquí lo
va a decir el agente en voz alta.
"""

from dataclasses import dataclass, field
from typing import Callable

from midgaror import modulo

bridge = modulo("bifrost_bridge")
tareas = modulo("tareas")
agenda = modulo("agenda")
habitos = modulo("habitos")
registro = modulo("registro")

# El parámetro `ruta` (y `rutas`) NO sale en los esquemas de abajo a propósito:
# es para que las pruebas escriban en temporales en vez de en el diario de
# verdad. El modelo no lo ve y `ejecutar()` no lo acepta de fuera, así que no
# hay forma de que el agente elija dónde escribe.
TEXTO = {"type": "string"}


@dataclass(frozen=True)
class Accion:
    """Una cosa que el agente sabe hacer, con cómo se la describimos al modelo."""

    nombre: str
    descripcion: str
    funcion: Callable
    propiedades: dict = field(default_factory=dict)
    obligatorios: tuple[str, ...] = ()

    def esquema(self) -> dict:
        """La acción en el formato de llamada a herramientas que usan los LLM."""
        return {
            "type": "function",
            "function": {
                "name": self.nombre,
                "description": self.descripcion,
                "parameters": {
                    "type": "object",
                    "properties": self.propiedades,
                    "required": list(self.obligatorios),
                },
            },
        }


# ---- las acciones ------------------------------------------------------
#
# Todas devuelven una frase corta: es lo que el agente contesta en voz alta.


def apuntar_en_diario(texto: str, fecha: str | None = None) -> str:
    """Escribe en la entrada del día, por el único camino que hay (ADR-009)."""
    bridge.escribir_entrada(texto, fecha=fecha)
    return f"Apuntado en el diario{' del ' + fecha if fecha else ''}."


def crear_tarea(texto: str, ruta=None) -> str:
    """Crea una tarea. El «cuándo» lo saca midgaror del propio texto."""
    tarea = tareas.agregar(texto, ruta=ruta)
    cuando = f" para el {tarea['fecha']}" if tarea.get("fecha") else ""
    return f"Tarea {tarea['id']} creada{cuando}: {tarea['texto']}."


def crear_cita(texto: str, ruta=None) -> str:
    """Crea una cita. Avisa si se solapa con otra: es lo primero que querrías saber."""
    cita, choques = agenda.agregar(texto, ruta=ruta)
    cuando = f" el {cita['fecha']}" if cita.get("fecha") else ""
    if cita.get("hora"):
        cuando += f" a las {cita['hora']}"
    aviso = f" Ojo, se solapa con {len(choques)}." if choques else ""
    return f"Cita {cita['id']} creada{cuando}: {cita['texto']}.{aviso}"


def marcar_habito(nombre: str, valor=None, fecha: str | None = None, ruta=None) -> str:
    """Marca un hábito. Sin `valor` es hecho/no hecho; con número, guarda el número."""
    # `marcar` devuelve (fecha, nombre, marca), en ese orden. Estaba mal
    # desempaquetado y salia "2026-09-11 el gimnasio: ✅": lo vio ejecutarlo,
    # no las pruebas, porque comprobaban que el nombre y la fecha SALIAN, no
    # en que sitio.
    dia, nombre_limpio, marca = habitos.marcar(
        nombre, fecha=fecha, ruta=ruta, valor=valor)
    return f"{nombre_limpio} el {dia}: {habitos.formato(marca)}."


def apuntar_registro(que: str, valor=None, unidad: str | None = None, ruta=None) -> str:
    """Apunta algo en el registro (ADR-012): «dos cafés», «hora y media de lectura»."""
    apunte = registro.apuntar(que, valor=valor, unidad=unidad, ruta=ruta)
    cuanto = f" ({apunte['valor']}{' ' + unidad if unidad else ''})" if "valor" in apunte else ""
    return f"Apuntado: {apunte['que']}{cuanto}."


def leer_diario(fecha: str | None = None) -> str:
    """Lee la entrada de un día. Leer nunca escribe: no crea la entrada ni la carpeta."""
    return bridge.leer_entrada(fecha)


def que_hay_hoy(fecha: str | None = None, rutas: dict | None = None) -> str:
    """Tareas, citas y hábitos del día, en un solo bloque."""
    rutas = rutas or {}
    partes = [
        tareas.resumen(ruta=rutas.get("tareas"), hoy=fecha),
        agenda.resumen(fecha, ruta=rutas.get("agenda")),
        habitos.resumen_dia(fecha, ruta=rutas.get("habitos")),
    ]
    vivas = [p.strip() for p in partes if p and p.strip()]
    return "\n\n".join(vivas) if vivas else "No hay nada apuntado para ese día."


ACCIONES: dict[str, Accion] = {
    a.nombre: a for a in (
        Accion(
            "apuntar_en_diario",
            "Escribe una frase en la entrada del diario del día. Para lo que ha "
            "pasado, lo que siente o lo que piensa, no para tareas ni citas.",
            apuntar_en_diario,
            {"texto": TEXTO,
             "fecha": {"type": "string", "description": "AAAA-MM-DD; vacío es hoy"}},
            ("texto",),
        ),
        Accion(
            "crear_tarea",
            "Crea una tarea pendiente. El texto puede decir cuándo "
            "(«el jueves», «mañana a las 10») y se guarda como fecha.",
            crear_tarea,
            {"texto": TEXTO},
            ("texto",),
        ),
        Accion(
            "crear_cita",
            "Crea una cita en la agenda, con su día y su hora. Para algo que "
            "ocurre a una hora concreta, no para una tarea suelta.",
            crear_cita,
            {"texto": TEXTO},
            ("texto",),
        ),
        Accion(
            "marcar_habito",
            "Marca un hábito del día: «he ido al gimnasio». Con número, guarda "
            "el número en vez de sí/no.",
            marcar_habito,
            {"nombre": TEXTO,
             "valor": {"type": "integer", "description": "1 a 10; vacío es sí/no"},
             "fecha": {"type": "string", "description": "AAAA-MM-DD; vacío es hoy"}},
            ("nombre",),
        ),
        Accion(
            "apuntar_registro",
            "Apunta algo que se cuenta o se mide: «dos cafés», «hora y media de "
            "lectura». Suma a lo del día, no lo sustituye.",
            apuntar_registro,
            {"que": TEXTO,
             "valor": {"type": "number", "description": "cuánto; vacío es «hecho»"},
             "unidad": {"type": "string", "description": "h, min, km…"}},
            ("que",),
        ),
        Accion(
            "leer_diario",
            "Lee lo escrito en el diario de un día.",
            leer_diario,
            {"fecha": {"type": "string", "description": "AAAA-MM-DD; vacío es hoy"}},
        ),
        Accion(
            "que_hay_hoy",
            "Qué hay para un día: tareas, citas y hábitos juntos.",
            que_hay_hoy,
            {"fecha": {"type": "string", "description": "AAAA-MM-DD; vacío es hoy"}},
        ),
    )
}


def catalogo() -> list[dict]:
    """Las acciones en el formato de llamada a herramientas de los LLM.

    Agnóstico de proveedor a propósito (ADR-018): elegir cerebro no debería
    obligar a reescribir esta capa.
    """
    return [accion.esquema() for accion in ACCIONES.values()]


def ejecutar(_accion: str, /, **argumentos) -> str:
    """Ejecuta una acción del catálogo. Devuelve la frase que dirá el agente.

    Solo pasa los argumentos **declarados en el esquema**. Un modelo que se
    invente un parámetro —`ruta`, por ejemplo, que es el que decide dónde se
    escribe— se queda sin él en vez de reventar o, peor, de colarlo.

    El primer parámetro es **posicional solo** (`/`) y lleva guion bajo por un
    fallo real: se llamaba `nombre`, y `marcar_habito` tiene un argumento que
    también se llama `nombre`, así que `ejecutar("marcar_habito",
    nombre="gimnasio")` moría con «got multiple values for argument 'nombre'».
    Ninguna prueba lo vio; lo vio ejecutarlo. Con `/` la colisión es imposible,
    se llame como se llame el argumento de la acción.
    """
    accion = ACCIONES.get(_accion)
    if accion is None:
        raise ValueError(
            f"acción desconocida: {_accion!r} (hay {', '.join(sorted(ACCIONES))})")
    permitidos = {k: v for k, v in argumentos.items() if k in accion.propiedades}
    faltan = [p for p in accion.obligatorios if permitidos.get(p) in (None, "")]
    if faltan:
        raise ValueError(f"{_accion}: falta {', '.join(faltan)}")
    return accion.funcion(**permitidos)
