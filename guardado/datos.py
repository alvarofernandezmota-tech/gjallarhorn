"""Dónde guarda sus cosas cada bot. Uno por negocio, y sin mezclarse.

Cada negocio es un bot con lo suyo: su conocimiento, sus frases, su voz, su
horario. Pero hasta aquí **los datos eran de todos**: un solo `avisos.json`
y un solo `clientes.json` para la máquina entera.

Eso está mal de dos maneras, y las dos se notan en cuanto hay un segundo bot:

- La peluquería saludaría por su nombre a un cliente que llamó a la otra
  cosa. La memoria de quien llama es del negocio al que llamó, no de la
  máquina donde corre el programa.
- Los avisos se mezclarían: quien lleva un negocio abriría el móvil y vería
  las citas del de al lado.

Así que los datos van por negocio:

    datos/<negocio>/agenda.json      las citas
    datos/<negocio>/clientes.json    quién ha llamado y qué suele pedir
    datos/<negocio>/avisos.json      el registro de llamadas

`GJALLARHORN_DATOS` sigue diciendo dónde está `datos/`, y sigue mereciendo la
pena sacarla del repo: ahí dentro hay nombres y teléfonos de clientes.

## Un proceso atiende a un bot

`usar()` fija de quién son los datos de este proceso. No es una variable
global por comodidad: es que un servidor atiende **un** negocio —su número de
teléfono, su voz, su agenda—, igual que `servidor.Comun.negocio`. Dos
negocios son dos procesos, y entonces cada uno tiene su contexto y no se
pisan. El día que haya que servir varios en el mismo proceso, esto es lo que
hay que cambiar, y por eso está en un sitio y no repartido por seis módulos.
"""

import os
import shutil
from pathlib import Path

VARIABLE = "GJALLARHORN_DATOS"

# De quién son los datos de este proceso. None = la carpeta de siempre, sin
# nombre de negocio: es lo que ve una prueba que no lo fija, y lo que había
# antes de que esto existiera.
_NEGOCIO: str | None = None


def raiz() -> Path:
    """La carpeta de datos. `GJALLARHORN_DATOS` manda; si no, `datos/` aquí."""
    valor = os.environ.get(VARIABLE, "").strip()
    # Desde el directorio de trabajo, NUNCA desde `__file__`: esta
    # libreria vive dentro de la aplicacion que la usa, y esta carpeta
    # es de la aplicacion. Con `__file__` acabaria dentro de hugin/.
    return Path(valor).expanduser() if valor else Path.cwd() / "datos"


def usar(negocio, migrar_lo_viejo: bool = True) -> list[str]:
    """Fija de qué negocio son los datos de este proceso.

    Acepta el nombre o el `Negocio` entero, que es lo que tiene a mano quien
    llama. Devuelve los ficheros que ha movido del reparto viejo, si los
    había, para que el arranque pueda decirlo en voz alta.
    """
    global _NEGOCIO
    _NEGOCIO = getattr(negocio, "ruta", None).name if hasattr(negocio, "ruta") else \
        (str(negocio) if negocio else None)
    return migrar() if (migrar_lo_viejo and _NEGOCIO) else []


def cual() -> str | None:
    """El negocio de este proceso, si se ha fijado."""
    return _NEGOCIO


def olvidar() -> None:
    """Vuelve a no tener negocio fijado. Para las pruebas."""
    global _NEGOCIO
    _NEGOCIO = None


def carpeta() -> Path:
    """La carpeta donde van los datos de este bot."""
    return raiz() / _NEGOCIO if _NEGOCIO else raiz()


def carpeta_de(negocio: str) -> Path:
    """La carpeta de un negocio concreto, se esté atendiendo o no.

    La usa la agenda, que siempre sabe de qué negocio es: no necesita que
    nadie le fije nada.
    """
    return raiz() / negocio if negocio else raiz()


def fichero(nombre: str) -> Path:
    """Un fichero de datos de este bot: `avisos.json`, `clientes.json`…"""
    return carpeta() / nombre


# Lo que había suelto en la raíz y ahora va dentro de la carpeta del negocio.
VIEJOS = ("avisos.json", "clientes.json")


def migrar() -> list[str]:
    """Mueve los datos del reparto viejo al del negocio. Devuelve qué movió.

    Se hace sola y una vez: quien ya tenía el bot funcionando tiene sus citas
    y sus clientes en la carpeta de antes, y perder eso por una mejora de
    organización sería el peor cambio posible. Si el fichero nuevo ya existe
    **no se toca nada**: dos ficheros con datos no se fusionan a ciegas.
    """
    if not _NEGOCIO:
        return []
    movidos = []
    destino = carpeta()
    for nombre in VIEJOS:
        viejo, nuevo = raiz() / nombre, destino / nombre
        if viejo.is_file() and not nuevo.exists():
            destino.mkdir(parents=True, exist_ok=True)
            shutil.move(str(viejo), str(nuevo))
            movidos.append(nombre)

    # La agenda vivía en `datos/agenda/<negocio>.json`.
    vieja = raiz() / "agenda" / f"{_NEGOCIO}.json"
    nueva = destino / "agenda.json"
    if vieja.is_file() and not nueva.exists():
        destino.mkdir(parents=True, exist_ok=True)
        shutil.move(str(vieja), str(nueva))
        movidos.append(f"agenda/{_NEGOCIO}.json")
    return movidos
