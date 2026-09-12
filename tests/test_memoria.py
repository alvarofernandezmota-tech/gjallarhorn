"""Pruebas de memoria.py — la ficha de quien llama.

Lo grueso de la memoria se prueba desde gjallarhorn, atendiendo llamadas de
verdad. Aquí va lo que **no** pasa por una llamada: `apuntar_nota()` la
escribe el dueño, no el cliente, así que ninguna conversación la ejercita y
se quedó sin una sola prueba desde que se escribió.
"""

import sys
import unittest
from pathlib import Path

# La raiz del repo **es** el paquete `hugin`, asi que lo que tiene que
# estar en el sys.path es la carpeta que lo contiene.
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ.parent))

import entorno  # noqa: E402

from hugin.mente import memoria  # noqa: E402


class CasoMemoria(unittest.TestCase):
    def setUp(self):
        entorno.aislar(self)


class TestLaNotaDelDueno(CasoMemoria):
    def test_se_apunta_y_se_lee(self):
        memoria.apuntar_nota("600111222", "prefiere por la mañana")
        self.assertEqual(memoria.ficha("600111222").notas,
                         ["prefiere por la mañana"])

    def test_se_apilan_sin_pisarse(self):
        memoria.apuntar_nota("600111222", "la primera")
        memoria.apuntar_nota("600111222", "la segunda")
        self.assertEqual(memoria.ficha("600111222").notas,
                         ["la primera", "la segunda"])

    def test_se_le_quitan_los_espacios_de_los_lados(self):
        memoria.apuntar_nota("600111222", "  con espacios  ")
        self.assertEqual(memoria.ficha("600111222").notas, ["con espacios"])

    def test_abre_ficha_si_no_habia(self):
        # El dueño puede apuntar algo de alguien que aún no ha llamado.
        ficha = memoria.apuntar_nota("600333444", "el del taller de al lado")
        self.assertIsNotNone(ficha)
        self.assertEqual(ficha.llamadas, 0)
        self.assertIsNotNone(ficha.primera, "una ficha nueva lleva fecha")

    def test_sin_telefono_no_escribe_nada(self):
        self.assertIsNone(memoria.apuntar_nota("", "una nota sin dueño"))
        self.assertEqual(memoria.fichas(), [])

    def test_el_derecho_al_olvido_se_lleva_las_notas(self):
        memoria.apuntar_nota("600111222", "algo personal")
        self.assertTrue(memoria.olvidar("600111222"))
        self.assertIsNone(memoria.ficha("600111222"))


if __name__ == "__main__":
    unittest.main()
