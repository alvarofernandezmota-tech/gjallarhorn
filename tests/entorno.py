"""Entorno de las pruebas: que ningún olvido escriba en los datos de verdad.

Se importa el primero en cada fichero de pruebas, antes que nada, porque las
rutas se resuelven al importar los módulos.

gjallarhorn no depende de ningún otro repo: aquí solo se desvían **sus** datos.
"""

import atexit
import os
import shutil
import tempfile


def _datos_de_mentira() -> None:
    """Raíces desechables para los avisos y el conocimiento."""
    for variable in ("GJALLARHORN_DATOS",):
        if os.environ.get(variable):
            continue
        tmp = tempfile.mkdtemp(prefix="gjallarhorn-pruebas-")
        os.environ[variable] = tmp
        atexit.register(shutil.rmtree, tmp, ignore_errors=True)


_datos_de_mentira()


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
