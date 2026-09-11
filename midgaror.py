"""Dónde está midgaror y cómo se importan sus módulos. En un solo sitio.

gjallarhorn no reimplementa nada del diario: llama a los módulos de midgaror,
los mismos que usa bifrost. Para eso hay que saber dónde está midgaror, y hay
dos situaciones:

- **Desplegado**: gjallarhorn es submódulo, en `midgaror/proyectos/gjallarhorn/`,
  así que la raíz está dos niveles por encima.
- **En desarrollo**: el repo está clonado suelto, en cualquier sitio. Ahí la
  ruta relativa no vale y hace falta decirlo con `MIDGAROR_RAIZ`.

Por eso la raíz es configurable y la ruta relativa es solo el valor por
defecto. Es la misma idea que `MIDGAROR_DATOS` en el ADR-016: sin la variable,
todo apunta a donde apuntaría.

**El `sys.path` se monta al importar este módulo.** Cambiar `MIDGAROR_RAIZ`
después no mueve nada: hay que ponerla antes del primer import.
"""

import importlib
import os
import sys
from pathlib import Path

VARIABLE = "MIDGAROR_RAIZ"

# gjallarhorn como submódulo vive en midgaror/proyectos/gjallarhorn/.
RAIZ_POR_DEFECTO = Path(__file__).resolve().parent.parent.parent


def raiz() -> Path:
    """La raíz de midgaror: `MIDGAROR_RAIZ` si está, o la posición de submódulo."""
    valor = os.environ.get(VARIABLE, "").strip()
    return Path(valor).expanduser().resolve() if valor else RAIZ_POR_DEFECTO


def _carpetas(base: Path) -> tuple[Path, ...]:
    """Las carpetas de midgaror que hay que tener en `sys.path`.

    `diario/` para bifrost_bridge, organizar_diario y almacen; las subcarpetas
    porque tareas.py, agenda.py, habitos.py y registro.py se importan por su
    nombre a secas, igual que en bifrost.
    """
    diario = base / "diario"
    return (diario, diario / "tareas", diario / "habitos",
            diario / "agenda", diario / "registro")


def _preparar() -> Path:
    base = raiz()
    if not (base / "diario" / "bifrost_bridge.py").exists():
        raise RuntimeError(
            f"No encuentro midgaror en {base}: falta diario/bifrost_bridge.py.\n"
            f"Si gjallarhorn no está dentro de midgaror/proyectos/, dilo con "
            f"{VARIABLE}=/ruta/a/midgaror antes de importar."
        )
    for carpeta in _carpetas(base):
        ruta = str(carpeta)
        if ruta not in sys.path:
            sys.path.insert(0, ruta)
    return base


MIDGAROR = _preparar()
DIARIO = MIDGAROR / "diario"


def modulo(nombre: str):
    """Un módulo de midgaror, por su nombre: `modulo("tareas")`.

    Es `importlib.import_module` con las rutas ya puestas. Como función y no
    como `import` para que quien lo use no arrastre el `# noqa: E402`.
    """
    return importlib.import_module(nombre)
