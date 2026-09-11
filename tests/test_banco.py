"""Pruebas del banco y de la medición.

Lo que se prueba aquí no es si el cerebro acierta —eso es lo que mide el banco—
sino que **el banco sepa detectar un fallo**. Un medidor que aprueba siempre es
peor que no medir: da una cifra y una falsa tranquilidad.
"""

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import banco  # noqa: E402
import medir  # noqa: E402

TRES = [
    ("apunta que hola", "apuntar_en_diario", "hola"),
    ("recuérdame comprar pan", "crear_tarea", "pan"),
    ("qué tengo hoy", "que_hay_hoy", ""),
]


class TestElBancoDetectaFallos(unittest.TestCase):
    def test_un_cerebro_perfecto_saca_todo(self):
        def perfecto(frase):
            for f, accion, trozo in TRES:
                if f == frase:
                    return accion, ({"texto": trozo} if trozo else {})
            raise AssertionError(frase)
        self.assertEqual(banco.evaluar(perfecto, TRES)["aciertos"], 3)

    def test_pilla_la_accion_equivocada(self):
        resultado = banco.evaluar(lambda f: ("crear_cita", {"texto": f}), TRES)
        self.assertEqual(resultado["aciertos"], 0)
        self.assertIn("dijo crear_cita", resultado["fallos"][0][2])

    def test_pilla_el_fallo_silencioso_de_perder_la_frase(self):
        # Acierta la acción y se deja la mitad del texto: el fallo que no se ve
        # mirando solo si «ha hecho algo».
        def amnesico(frase):
            for f, accion, _ in TRES:
                if f == frase:
                    return accion, {"texto": ""}
            raise AssertionError(frase)
        resultado = banco.evaluar(amnesico, TRES)
        self.assertEqual(resultado["aciertos"], 1, "solo la pregunta, que no lleva trozo")
        self.assertIn("perdió", resultado["fallos"][0][2])

    def test_un_cerebro_que_revienta_cuenta_como_fallo_y_no_tumba_la_medicion(self):
        def roto(_):
            raise RuntimeError("el modelo no responde")
        resultado = banco.evaluar(roto, TRES)
        self.assertEqual(resultado["aciertos"], 0)
        self.assertIn("reventó", resultado["fallos"][0][2])


class TestElBancoEstaBienFormado(unittest.TestCase):
    def test_toda_frase_espera_una_accion_que_existe(self):
        import acciones
        for frase, esperada, _ in banco.FRASES:
            self.assertIn(esperada, acciones.ACCIONES, f"«{frase}» espera {esperada}")

    def test_no_hay_frases_repetidas(self):
        frases = [f for f, _, _ in banco.FRASES]
        repetidas = {f for f in frases if frases.count(f) > 1}
        self.assertEqual(repetidas, set(), f"repetidas: {repetidas}")

    def test_hay_frases_adversarias_de_verdad(self):
        # Si el banco vuelve a aprobar al 100 %, o el cerebro ha mejorado o
        # alguien ha quitado las frases incómodas. Las dos cosas hay que verlas.
        import cerebro
        resultado = banco.evaluar(cerebro.decidir)
        self.assertLess(
            resultado["acierto"], 1.0,
            "el banco aprueba al 100 %: o se ha arreglado el cerebro y hay que "
            "meter frases nuevas, o se han quitado las que fallaban")

    def test_cada_pregunta_no_espera_argumentos(self):
        # Una pregunta que llevara texto escribiría la pregunta en el diario.
        for frase, esperada, trozo in banco.FRASES:
            if esperada in ("que_hay_hoy", "leer_diario"):
                self.assertEqual(trozo, "", f"«{frase}» es una pregunta")


class TestLaMedicion(unittest.TestCase):
    def test_mide_tiempos_ademas_de_aciertos(self):
        resultado = medir.medir(lambda f: ("apuntar_en_diario", {"texto": f}), TRES)
        self.assertIn("ms_mediana", resultado)
        self.assertIn("ms_peor", resultado)
        self.assertGreaterEqual(resultado["ms_peor"], resultado["ms_mediana"])

    def test_el_informe_dice_acierto_latencia_y_en_que_falla(self):
        resultado = medir.medir(lambda f: ("crear_cita", {"texto": f}), TRES)
        texto = medir.informe("de prueba", resultado)
        self.assertIn("Acierto", texto)
        self.assertIn("Latencia", texto)
        self.assertIn("esperaba", texto)


if __name__ == "__main__":
    unittest.main()
