"""Pruebas de midgaror.py — encontrar midgaror, o decir claramente que no está.

El fallo que esto evita es el más aburrido y el más caro: un `ImportError` de
`tareas` tres capas más abajo, que no dice ni que el problema es la ruta ni
cómo arreglarlo.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401 — fija MIDGAROR_DATOS antes de cualquier import

import midgaror  # noqa: E402


def _en_proceso_aparte(codigo: str, variables: dict) -> subprocess.CompletedProcess:
    """midgaror.py monta el sys.path AL IMPORTARSE, así que cambiar la variable
    dentro del mismo proceso no prueba nada. Cada caso, su intérprete."""
    env = {**os.environ, **variables, "PYTHONPATH": str(RAIZ)}
    return subprocess.run([sys.executable, "-c", codigo],
                          capture_output=True, text=True, env=env)


class TestDondeEstaMidgaror(unittest.TestCase):
    def test_la_variable_manda_sobre_la_posicion_de_submodulo(self):
        codigo = "import midgaror; print(midgaror.raiz())"
        with tempfile.TemporaryDirectory() as tmp:
            # Una raíz falsa pero válida: lo que se comprueba es de dónde sale.
            falsa = Path(tmp)
            (falsa / "diario").mkdir()
            (falsa / "diario" / "bifrost_bridge.py").write_text("", encoding="utf-8")
            salida = _en_proceso_aparte(codigo, {"MIDGAROR_RAIZ": str(falsa)})
            self.assertEqual(salida.returncode, 0, salida.stderr)
            self.assertEqual(salida.stdout.strip(), str(falsa.resolve()))

    def test_sin_variable_busca_donde_estaria_de_submodulo(self):
        self.assertEqual(
            midgaror.RAIZ_POR_DEFECTO, RAIZ.parent.parent,
            "de submódulo, gjallarhorn vive en midgaror/proyectos/gjallarhorn/")

    def test_si_no_encuentra_midgaror_lo_dice_y_dice_como_arreglarlo(self):
        codigo = "import midgaror"
        with tempfile.TemporaryDirectory() as tmp:
            salida = _en_proceso_aparte(codigo, {"MIDGAROR_RAIZ": tmp})
            self.assertNotEqual(salida.returncode, 0, "debería haber fallado")
            self.assertIn("No encuentro midgaror", salida.stderr)
            self.assertIn("MIDGAROR_RAIZ", salida.stderr,
                          "el error no dice cómo arreglarlo")

    def test_las_carpetas_de_los_cuatro_modelos_estan_en_el_camino(self):
        # tareas.py, agenda.py, habitos.py y registro.py se importan por su
        # nombre a secas, así que cada subcarpeta tiene que estar.
        nombres = {c.name for c in midgaror._carpetas(Path("/x"))}
        self.assertEqual(nombres, {"diario", "tareas", "habitos", "agenda", "registro"})

    def test_modulo_trae_los_modulos_de_verdad(self):
        self.assertTrue(hasattr(midgaror.modulo("tareas"), "agregar"))
        self.assertTrue(hasattr(midgaror.modulo("bifrost_bridge"), "escribir_entrada"))


if __name__ == "__main__":
    unittest.main()
