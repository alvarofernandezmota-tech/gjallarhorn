"""Pruebas de cómo se pide hora por teléfono de verdad.

Dos fallos encontrados escuchando llamadas, no leyendo código. Los dos
acababan igual de mal y por motivos distintos:

- **«Quiero un tinte»** no lleva la palabra «cita» por ningún lado, y se
  llevaba un «tomo nota y le devolvemos la llamada». Por teléfono se pide
  así la mitad de las veces: quien llama a pedir hora se iba con un recado
  y sin hora.
- **«Se llama Carmen»** se apuntaba como nombre del cliente: «Se Llama
  Carmen». Y como el nombre se guarda en la ficha del número, a partir de
  ahí el bot saludaba «Hola, Se Llama Carmen» en cada llamada. Un fallo de
  una frase que ensucia los datos para siempre.
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
    negocio = "peluqueria"

    def setUp(self):
        entorno.aislar(self)
        datos.olvidar()
        self.addCleanup(datos.olvidar)
        datos.usar(self.negocio)
        self.n = negocios.cargar(self.negocio)

    def dice(self, *frases):
        llamada = recepcion.conversacion_de(self.n)
        return [llamada.atender(f).texto for f in frases], llamada


class TestPedirHoraSinDecirCita(Caso):
    def test_quiero_un_tinte_es_pedir_hora(self):
        dicho, _ = self.dice("quiero un tinte")
        self.assertIn("tinte", dicho[0].lower())
        self.assertNotIn("tomo nota", dicho[0].lower())

    def test_lo_mismo_con_otras_formas_de_decirlo(self):
        for frase in ("necesito un recogido", "quería unas mechas",
                      "me gustaría un tinte", "ponme un tinte"):
            with self.subTest(frase=frase):
                dicho, _ = self.dice(frase)
                self.assertNotIn("tomo nota", dicho[0].lower(), frase)

    def test_si_el_servicio_es_ambiguo_se_pregunta_cual(self):
        # Hay cuatro cortes. Adivinar es como se acaba cantando el precio
        # del caro cuando han pedido el barato: se pregunta.
        dicho, _ = self.dice("quiero un corte")
        self.assertIn("servicio", dicho[0].lower())
        self.assertNotIn("tomo nota", dicho[0].lower())

    def test_y_se_puede_terminar_la_cita(self):
        dicho, llamada = self.dice("quiero un tinte", "el jueves a las once",
                                   "me llamo Marta")
        self.assertIn("Reservada", dicho[-1])
        self.assertIn("Marta", dicho[-1])

    def test_lo_que_no_es_un_servicio_sigue_siendo_recado(self):
        # La regla no puede dispararse con cualquier «quiero».
        for frase in ("quiero un café", "quiero hablar con el encargado"):
            with self.subTest(frase=frase):
                dicho, _ = self.dice(frase)
                self.assertNotIn("¿Qué día", dicho[0], frase)

    def test_preguntar_el_precio_sigue_siendo_el_precio(self):
        # «Quiero saber cuánto vale un tinte» lleva «quiero» y un servicio, y
        # no es una cita. El precio va antes, y tiene que seguir yendo antes.
        dicho, _ = self.dice("quiero saber cuánto vale un tinte")
        self.assertIn("45", dicho[0])
        self.assertNotIn("¿Qué día", dicho[0])

    def test_preguntar_el_horario_sigue_siendo_el_horario(self):
        dicho, _ = self.dice("quiero saber el horario")
        self.assertIn("10:00", dicho[0])


class TestElTallerTambien(Caso):
    """El taller dice las cosas con otras palabras que su tabla de precios."""

    negocio = "taller"

    def test_se_reconoce_aunque_no_diga_el_nombre_exacto(self):
        # Dicen «cambiar las ruedas»; el servicio es «Cambio de neumáticos».
        dicho, _ = self.dice("quiero cambiar las ruedas")
        self.assertIn("neumáticos", dicho[0].lower())
        self.assertNotIn("tomo nota", dicho[0].lower())

    def test_y_tutea_al_hacerlo(self):
        dicho, _ = self.dice("quiero cambiar las ruedas")
        self.assertIn("te viene bien", dicho[0])


class TestElNombreDeOtraPersona(Caso):
    def test_se_llama_carmen_es_carmen(self):
        self.assertEqual(recepcion._nombre_en("se llama Carmen", self.n.conocimiento),
                         ("Carmen", False))

    def test_pedir_para_otro_no_es_presentarse(self):
        # Quien llama no se llama Carmen: su madre sí. El segundo valor dice
        # justo eso, y de él depende que no se le cambie el nombre a la ficha.
        _, se_presenta = recepcion._nombre_en("es para mi madre, que se llama Carmen",
                                              self.n.conocimiento)
        self.assertFalse(se_presenta)
        _, se_presenta = recepcion._nombre_en("soy Marta", self.n.conocimiento)
        self.assertTrue(se_presenta)

    def test_la_cita_entera_para_otra_persona(self):
        dicho, llamada = self.dice("quiero un corte de señora",
                                   "el jueves a las once", "se llama Carmen")
        self.assertIn("Carmen", dicho[-1])
        self.assertNotIn("Se Llama", dicho[-1])

    def test_a_secas_tampoco_se_come_el_se_llama(self):
        self.assertEqual(recepcion._nombre_a_secas("se llama Carmen"), "Carmen")

    def test_un_servicio_sigue_sin_ser_un_nombre(self):
        self.assertIsNone(recepcion._nombre_en("la cita de tinte", self.n.conocimiento))


if __name__ == "__main__":
    unittest.main()
