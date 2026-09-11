"""Entorno de las pruebas: que ningún olvido escriba en los datos de verdad.

Se importa el primero en cada fichero de pruebas, antes que nada, porque las
rutas se resuelven al importar los módulos.

gjallarhorn no depende de midgaror: aquí solo se desvían **sus** datos.
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
