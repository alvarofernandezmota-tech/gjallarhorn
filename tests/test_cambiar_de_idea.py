"""Pruebas de dos cosas que sonaban a roto por teléfono.

**Cambiar de servicio a mitad.** «Ah no, mejor unas mechas» no lo recogía
nadie: `_rellenar_con` mete fecha, hora y nombre, pero nunca el servicio.
La frase caía hasta la FAQ, que contestaba si hace falta cita para las
mechas y lo pegaba a la pregunta pendiente. Quien llamaba oía un párrafo
que no había pedido y luego la pregunta.

**Preguntar por la cita no es pedirla.** «¿Hace falta cita para las
mechas?» lleva la palabra «cita» y abría una. Quien llamaba a informarse
se encontraba con «¿qué día le viene bien?».

Las dos se distinguen por lo mismo: nombrar un servicio no dice qué
quieres hacer con él. Hace falta la marca —«mejor», «hace falta»— y por eso
las dos listas están en `frases.toml`, editables por negocio.
"""

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

from guardado import datos  # noqa: E402
from mente import recepcion  # noqa: E402
from negocio import negocio as negocios  # noqa: E402


class Caso(unittest.TestCase):
    def setUp(self):
        entorno.aislar(self)
        datos.olvidar()
        self.addCleanup(datos.olvidar)
        datos.usar("peluqueria")
        self.n = negocios.cargar("peluqueria")

    def conversacion(self, *frases):
        llamada = recepcion.conversacion_de(self.n, ahora=entorno.AHORA)
        return [llamada.atender(f).texto for f in frases], llamada


class TestCambiarDeServicioAMitad(Caso):
    def test_se_cambia_y_no_se_cuela_un_parrafo_de_la_faq(self):
        dicho, _ = self.conversacion("quiero un tinte", "ah no, mejor unas mechas")
        self.assertIn("mechas", dicho[1].lower())
        # Lo que se colaba: la respuesta de la FAQ pegada delante.
        self.assertNotIn("se puede pasar", dicho[1])
        self.assertNotIn("recogidos", dicho[1])

    def test_una_sola_frase_por_turno(self):
        # Dos respuestas pegadas es lo que hace que suene a robot roto: se
        # oye un párrafo que nadie ha pedido y luego la pregunta.
        dicho, _ = self.conversacion("quiero un tinte", "ah no, mejor unas mechas")
        self.assertLessEqual(dicho[1].count("."), 2, dicho[1])

    def test_la_cita_se_cierra_con_el_servicio_nuevo(self):
        dicho, _ = self.conversacion("quiero un tinte", "ah no, mejor unas mechas",
                                     "el jueves a las once", "soy Marta")
        self.assertIn("mechas", dicho[-1].lower())
        self.assertNotIn("tinte", dicho[-1].lower())

    def test_valen_varias_formas_de_cambiar_de_idea(self):
        for cambio in ("mejor unas mechas", "en vez de eso unas mechas",
                       "prefiero unas mechas", "no, unas mechas"):
            with self.subTest(cambio=cambio):
                dicho, _ = self.conversacion("quiero un tinte", cambio)
                self.assertIn("mechas", dicho[1].lower(), cambio)

    def test_preguntar_el_precio_a_mitad_sigue_dando_el_precio(self):
        # «¿Y cuánto vale?» en mitad de una cita es una pregunta, no un
        # cambio de servicio. El precio va antes, y tiene que seguir yendo.
        dicho, _ = self.conversacion("quiero un tinte", "¿y cuánto vale?")
        self.assertIn("45", dicho[1])


class TestPreguntarPorLaCitaNoEsPedirla(Caso):
    def test_hace_falta_cita_se_contesta_no_se_abre_una(self):
        dicho, llamada = self.conversacion("¿hace falta cita para las mechas?")
        self.assertNotIn("¿Qué día", dicho[0])
        self.assertNotIn("qué servicio", dicho[0].lower())

    def test_otras_formas_de_preguntar_lo_mismo(self):
        for pregunta in ("¿hay que pedir cita?", "¿es necesario cita?",
                         "¿puedo ir sin cita?"):
            with self.subTest(pregunta=pregunta):
                dicho, _ = self.conversacion(pregunta)
                self.assertNotIn("¿Qué día", dicho[0], pregunta)

    def test_pedir_cita_de_verdad_sigue_abriendo_una(self):
        # La guarda no puede comerse las peticiones de verdad.
        for peticion in ("quiero cita", "necesito una cita para el jueves",
                         "¿me das hora para el jueves?"):
            with self.subTest(peticion=peticion):
                dicho, llamada = self.conversacion(peticion)
                self.assertIsNotNone(llamada.cita, peticion)

    def test_preguntar_a_mitad_de_una_cita_no_la_rompe(self):
        dicho, llamada = self.conversacion("quiero un tinte",
                                           "¿hace falta cita para las mechas?",
                                           "el jueves a las once", "soy Marta")
        # Se contesta la pregunta y la cita del tinte sigue en pie.
        self.assertIn("tinte", dicho[-1].lower())
        self.assertIn("Reservada", dicho[-1])


class TestNombrarNoEsPedir(Caso):
    """El peor de los tres, y el que encontró la prueba de arriba.

    El servicio de la cita se ponía cada vez que se nombraba uno, fuera
    para lo que fuera. Así que quien pedía un tinte y luego preguntaba
    «¿hace falta cita para las mechas?» acababa citado **para mechas**, sin
    que nadie se lo dijera. Se entera el día que va a la peluquería.
    """

    def test_preguntar_por_otro_servicio_no_cambia_la_cita(self):
        _, llamada = self.conversacion("quiero un tinte",
                                       "¿hace falta cita para las mechas?")
        self.assertEqual(llamada.cita.servicio, "Tinte")

    def test_ni_preguntar_su_precio(self):
        _, llamada = self.conversacion("quiero un tinte",
                                       "¿y cuánto valen las mechas?")
        self.assertEqual(llamada.cita.servicio, "Tinte")

    def test_pero_de_lo_hablado_si_se_entera(self):
        # Que no cambie la cita no quiere decir que pierda el hilo: «¿y
        # cuánto dura?» detrás de las mechas contesta lo de las mechas.
        dicho, _ = self.conversacion("quiero un tinte",
                                     "¿y cuánto valen las mechas?", "¿y cuánto dura?")
        self.assertIn("mechas", dicho[-1].lower())

    def test_decirlo_con_todas_las_letras_si_lo_cambia(self):
        _, llamada = self.conversacion("quiero un tinte", "mejor unas mechas")
        self.assertEqual(llamada.cita.servicio, "Mechas")

    def test_y_si_no_habia_ninguno_se_pone(self):
        _, llamada = self.conversacion("quiero cita", "un tinte")
        self.assertEqual(llamada.cita.servicio, "Tinte")


if __name__ == "__main__":
    unittest.main()
