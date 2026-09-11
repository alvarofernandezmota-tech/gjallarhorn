"""Aísla las pruebas de los datos de verdad. Se importa **antes que nada**.

Esto existe por un fallo real del 2026-09-11: una prueba llamaba a
`acciones.ejecutar(...)` sin pasar `ruta`, así que la escritura se fue a las
rutas por defecto —el `tareas.json` y el `registro.json` reales de Álvaro— y
acabó **commiteada** en midgaror. Cuatro tareas «algo» y cuatro cafés que él no
había apuntado, y un `registro/datos/` que no existía y pasó a existir.

Lo grave no fue la basura, que se limpia. Fue que la prueba que lo hacía era
justo la que se escribió para cazar otro fallo: el cuidado no basta, porque el
cuidado se olvida. Hace falta que sea **imposible**.

Así que aquí se fija `MIDGAROR_DATOS` (ADR-016) a un temporal antes de que
nadie importe nada. Los módulos del diario calculan su ruta de datos **al
importarse**, así que puestos después ya no valdrían: por eso esto va arriba
del todo en cada fichero de pruebas, antes que `import acciones`.

Con esto, una prueba que se olvide de pasar `ruta` escribe en el temporal en
vez de en el diario. El olvido deja de costar caro.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent


def _midgaror() -> None:
    """Dónde está midgaror, si no se ha dicho ya."""
    if os.environ.get("MIDGAROR_RAIZ"):
        return
    candidato = _RAIZ.parent / "midgaror"
    if (candidato / "diario" / "bifrost_bridge.py").exists():
        os.environ["MIDGAROR_RAIZ"] = str(candidato)


def _datos_de_mentira() -> None:
    """Una raíz de datos desechable, para que ningún olvido llegue al diario."""
    if os.environ.get("MIDGAROR_DATOS"):
        return
    tmp = tempfile.mkdtemp(prefix="gjallarhorn-pruebas-")
    os.environ["MIDGAROR_DATOS"] = tmp
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)


_midgaror()
_datos_de_mentira()

DATOS = Path(os.environ["MIDGAROR_DATOS"])
