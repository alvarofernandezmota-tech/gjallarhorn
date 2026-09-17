"""Entorno de las pruebas: que ningún olvido escriba en los datos de verdad.

Se importa el primero en cada fichero de pruebas, antes que nada, porque las
rutas se resuelven al importar los módulos.

gjallarhorn no depende de ningún otro repo: aquí solo se desvían **sus** datos.
"""

import atexit
from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile
from zoneinfo import ZoneInfo


# El reloj de la suite: viernes 11 de septiembre de 2026, a las diez.
#
# Una prueba que escribe una fecha a mano y deja correr el reloj de verdad
# caduca: la agenda no reserva en el pasado, así que el día que esa fecha
# quedó atrás se pusieron 21 pruebas en rojo solas, sin que nadie tocara el
# código. Quien fije una fecha, que fije también el reloj —`ahora=AHORA` al
# construir la agenda o la llamada— y así la suite dice lo mismo hoy que
# dentro de un año.
AHORA = datetime(2026, 9, 11, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))


# El negocio con el que se prueba es **de las pruebas**, y vive en
# `tests/negocios/`. Antes se usaba el que trae el repo en `negocios/`, y eso
# convertía el fichero de configuración de un negocio de verdad en parte de la
# suite: el día que su dueño lo editó —que es lo que el README le dice que
# puede hacer— se cayeron 291 pruebas que no tenían nada que ver.
NEGOCIOS = Path(__file__).resolve().parent / "negocios"


def _negocio_de_pruebas() -> None:
    # Sin `setdefault`: las pruebas usan **su** negocio pase lo que pase. Con
    # setdefault, correr la suite en una terminal donde estuviera exportada la
    # variable —cosa que pasa en cuanto pruebas algo a mano— hacía que la
    # suite mirase otros ficheros y fallara por algo que no era el código.
    os.environ["GJALLARHORN_NEGOCIOS"] = str(NEGOCIOS)


def _datos_de_mentira() -> None:
    """Raíces desechables para los avisos y el conocimiento."""
    for variable in ("GJALLARHORN_DATOS",):
        if os.environ.get(variable):
            continue
        tmp = tempfile.mkdtemp(prefix="gjallarhorn-pruebas-")
        os.environ[variable] = tmp
        atexit.register(shutil.rmtree, tmp, ignore_errors=True)


# Las credenciales del dueño NO entran en la suite. `telefonia` y `avisar`
# leen el `.env` de la raíz del repo para saber si hay teléfono o Telegram, y
# eso hacía que las pruebas dependieran de la máquina: en un portátil recién
# clonado pasaban, y en el de quien ya tiene el bot funcionando fallaban
# cuatro —las que comprueban justo que «sin teléfono no está listo»—, porque
# veían el token de verdad.
#
# Una suite que se comporta distinto según lo que tengas configurado no dice
# nada. Y de paso: correr las pruebas no tiene por qué cargar tus secretos.
CREDENCIALES = ("GJALLARHORN_TELEFONO_TOKEN", "GJALLARHORN_TELEFONO_CLAVE_PUBLICA",
                "GJALLARHORN_TELEFONO_CLAVE_SIGNALWIRE", "GJALLARHORN_TELEFONO_VOZ",
                "GJALLARHORN_TELEGRAM_TOKEN", "GJALLARHORN_TELEGRAM_CHAT",
                "GJALLARHORN_TELEGRAM_TIPOS", "ANTHROPIC_API_KEY",
                "GJALLARHORN_LLM", "GJALLARHORN_LLM_MODELO")


def _sin_credenciales_de_verdad() -> None:
    """Quita las credenciales del entorno y esconde el .env del repo.

    Lo segundo hace falta además de lo primero: `avisar._leer_env()` va a
    buscar el fichero cada vez, así que no basta con limpiar `os.environ`.
    Se apunta a un `.env` que no existe. **RAIZ no se toca**: sigue siendo la
    raíz del repo de verdad, que es lo que dicen otras pruebas.
    """
    for variable in CREDENCIALES:
        os.environ.pop(variable, None)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from dueno import avisar
    vacia = tempfile.mkdtemp(prefix="gjallarhorn-sin-env-")
    atexit.register(shutil.rmtree, vacia, ignore_errors=True)
    avisar.FICHERO_ENV = Path(vacia) / ".env"


_datos_de_mentira()
_negocio_de_pruebas()
_sin_credenciales_de_verdad()


def aislar(caso) -> str:
    """Datos propios para **este** caso de prueba. Devuelve la carpeta.

    `_datos_de_mentira` aparta los datos del proceso entero, pero dentro del
    proceso todos los casos comparten la misma carpeta: la agenda, los avisos
    y el registro de clientes son los mismos para todos. Una prueba que
    reserva una cita le cambia el mundo a la siguiente, y el fallo aparece
    **solo al correr la suite entera**, que es la peor forma de descubrirlo.

    Las rutas se leen en cada llamada, no al importar, así que basta con
    mover la variable y devolverla a su sitio al acabar.
    """
    tmp = tempfile.mkdtemp(prefix="gjallarhorn-caso-")
    antes = os.environ.get("GJALLARHORN_DATOS")
    os.environ["GJALLARHORN_DATOS"] = tmp

    def devolver():
        if antes is None:
            os.environ.pop("GJALLARHORN_DATOS", None)
        else:
            os.environ["GJALLARHORN_DATOS"] = antes
        shutil.rmtree(tmp, ignore_errors=True)

    caso.addCleanup(devolver)
    return tmp
