"""Pruebas de cerebro.py — el LLM entra solo donde las reglas no llegan.

Sin clave ni red: `preguntar` se sustituye por una función que devuelve lo
que se le diga. Lo que se prueba no es el modelo —eso es del modelo—, es que
lo que devuelva se atienda por el mismo camino que las reglas, y que **no
pueda colar ni un precio ni un servicio que no esté en la tabla**.
"""

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

import cerebro  # noqa: E402
import negocio as negocios  # noqa: E402
import recepcion  # noqa: E402


def modelo_que_dice(**campos):
    """Un `preguntar` de mentira: siempre contesta lo mismo."""
    base = {"intencion": "otro", "servicio": None, "cuando": None, "nombre": None}
    def preguntar(frase, servicios):
        return {**base, **campos}
    return preguntar


def modelo_roto(frase, servicios):
    raise ConnectionError("sin red")


class CasoCerebro(unittest.TestCase):
    def setUp(self):
        self.negocio = negocios.cargar("peluqueria")
        self.base = self.negocio.conocimiento

    def llamada(self, preguntar):
        return recepcion.Conversacion(self.base, preguntar=preguntar)


class TestEntender(CasoCerebro):
    def test_devuelve_lo_que_el_modelo_entendio(self):
        e = cerebro.entender("hacéis mechas?", self.base,
                             preguntar=modelo_que_dice(intencion="precio", servicio="Mechas"))
        self.assertEqual((e.intencion, e.servicio), ("precio", "Mechas"))

    def test_un_servicio_que_no_esta_en_la_tabla_se_descarta(self):
        # Diga lo que diga el modelo, un servicio fuera de la tabla no existe.
        e = cerebro.entender("alisado?", self.base,
                             preguntar=modelo_que_dice(intencion="precio", servicio="Alisado"))
        self.assertIsNone(e.servicio)

    def test_una_intencion_inventada_se_descarta_entera(self):
        self.assertIsNone(cerebro.entender("x", self.base,
                                           preguntar=modelo_que_dice(intencion="reembolso")))

    def test_si_falla_devuelve_none_y_no_revienta(self):
        self.assertIsNone(cerebro.entender("x", self.base, preguntar=modelo_roto))

    def test_sin_clave_no_hay_modelo(self):
        import os
        real = dict(os.environ)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(real)))
        import avisar
        leer = avisar._leer_env
        avisar._leer_env = lambda *a, **k: None
        self.addCleanup(setattr, avisar, "_leer_env", leer)
        self.assertFalse(cerebro.configurado())
        self.assertIsNone(cerebro.entender("x", self.base))

    def test_mide_cuanto_tarda(self):
        e = cerebro.entender("x", self.base, preguntar=modelo_que_dice(intencion="horario"))
        self.assertGreaterEqual(e.ms, 0)


class TestElEsquema(unittest.TestCase):
    def test_el_servicio_solo_puede_ser_de_la_tabla_o_nulo(self):
        esquema = cerebro._esquema(["Tinte", "Mechas"])
        self.assertEqual(esquema["properties"]["servicio"]["enum"], ["Tinte", "Mechas", None])
        self.assertFalse(esquema["additionalProperties"])
        self.assertEqual(set(esquema["required"]), {"intencion", "servicio", "cuando", "nombre"})

    def test_las_instrucciones_llevan_la_lista_y_prohiben_inventar(self):
        texto = cerebro._instrucciones(["Tinte"])
        self.assertIn("- Tinte", texto)
        self.assertIn("Nunca inventes", texto)


class TestEnLaConversacion(CasoCerebro):
    def test_donde_las_reglas_no_llegan_entra_el_modelo(self):
        # «lo del color ese» no lleva ninguna palabra de precio: por reglas es
        # un recado. El modelo entiende que pregunta por el tinte.
        dicho = self.llamada(modelo_que_dice(intencion="precio", servicio="Tinte")) \
            .atender("oye, ¿hacéis lo del color ese?").texto
        self.assertIn("45", dicho)

    def test_las_reglas_van_primero_y_el_modelo_no_las_pisa(self):
        # Con «cuánto vale» las reglas entienden; el modelo ni se consulta.
        llamada = self.llamada(modelo_roto)
        self.assertIn("45", llamada.atender("¿cuánto vale un tinte?").texto)

    def test_el_modelo_no_puede_colar_un_precio(self):
        # Servicio fuera de la tabla → «no tengo ese servicio», nunca un número.
        dicho = self.llamada(modelo_que_dice(intencion="precio", servicio="Alisado")) \
            .atender("¿hacéis alisado?").texto
        self.assertIn("No tengo ese servicio", dicho)
        self.assertNotRegex(dicho, r"\d+ €")

    def test_una_cita_entendida_por_el_modelo_sigue_el_camino_normal(self):
        llamada = self.llamada(modelo_que_dice(
            intencion="cita", servicio="Tinte", cuando="el jueves a las cinco de la tarde"))
        dicho = llamada.atender("me gustaría pasarme el jueves a las cinco de la tarde a por un tinte").texto
        self.assertIn("nombre", dicho.lower())      # día y hora ya puestos: falta el nombre
        self.assertEqual(llamada.cita.servicio, "Tinte")
        self.assertEqual(llamada.cita.hora, "17:00")

    def test_si_el_modelo_falla_se_toma_nota_como_siempre(self):
        dicho = self.llamada(modelo_roto).atender("una cosa rara").texto
        self.assertIn("devolvemos la llamada", dicho)

    def test_la_despedida_entendida_por_el_modelo(self):
        dicho = self.llamada(modelo_que_dice(intencion="despedida")).atender("pues nada, hasta otra").texto
        self.assertIn("Hasta luego", dicho)


if __name__ == "__main__":
    unittest.main()
