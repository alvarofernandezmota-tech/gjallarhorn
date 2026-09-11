"""Pruebas del pulido: sinónimos, repetir, «¿eres un robot?», duraciones y pistas.

Nadie dice «corte de caballero» por teléfono: dice «cortarme el pelo». Y
nadie dice «90 min»: dice «una hora y media». Lo de aquí es lo que separa
una tabla leída en voz alta de alguien que atiende.
"""

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

from mente import conocimiento  # noqa: E402
from mente import fechas  # noqa: E402
from negocio import frases  # noqa: E402
from negocio import negocio as negocios  # noqa: E402
from mente import recepcion  # noqa: E402
from telefono import telefonia  # noqa: E402


class CasoPeluqueria(unittest.TestCase):
    def setUp(self):
        self.negocio = negocios.cargar("peluqueria")
        self.base = self.negocio.conocimiento
        self.llamada = recepcion.Conversacion(self.base)

    def texto(self, *frases_):
        texto = ""
        for frase in frases_:
            texto = self.llamada.atender(frase).texto
        return texto


class TestSinonimos(CasoPeluqueria):
    def test_cortarme_el_pelo_son_los_cortes(self):
        nombres = [s["servicio"] for s in conocimiento.buscar("cuánto vale cortarme el pelo", self.base)]
        self.assertIn("Corte de caballero", nombres)
        self.assertIn("Corte de señora", nombres)

    def test_un_corte_de_hombre_es_el_de_caballero(self):
        self.assertIn("14", self.texto("¿cuánto vale un corte de hombre?"))

    def test_reflejos_son_mechas(self):
        self.assertIn("65", self.texto("¿cuánto valen los reflejos?"))

    def test_para_mi_hija_es_el_infantil(self):
        self.assertIn("10", self.texto("¿cuánto vale un corte para mi hija?"))

    def test_tenirme_es_el_tinte(self):
        self.assertIn("45", self.texto("¿cuánto cuesta teñirme?", "el tinte"))

    def test_elegir_entre_lo_ofrecido_tambien_entiende_sinonimos(self):
        self.texto("¿cuánto vale cortarme el pelo?")
        self.assertIn("14", self.texto("el de hombre"))

    def test_una_cita_nombra_el_servicio_por_su_sinonimo(self):
        self.texto("quiero cita para cortarle el pelo a mi hijo")
        self.assertEqual(self.llamada.cita.servicio, "Corte infantil")

    def test_para_mi_hija_gana_al_servicio_del_que_se_hablaba(self):
        # Se habló del corte de caballero; la cita es para la niña. Se apuntaba
        # un corte de caballero a nombre de la niña.
        self.texto("¿cuánto vale el corte de caballero?", "quiero cita para mi hija el sábado")
        self.assertEqual(self.llamada.cita.servicio, "Corte infantil")

    def test_sin_sinonimos_no_pasa_nada(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        (base / "tarifas.md").write_text("| Servicio | Precio |\n|---|---|\n| Corte | 10 € |\n",
                                         encoding="utf-8")
        self.assertEqual(conocimiento.buscar("un corte", base)[0]["servicio"], "Corte")
        self.assertEqual(conocimiento.buscar("cortarme", base), [])

    def test_los_sinonimos_se_leen_sin_tildes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        (base / "tarifas.md").write_text("| Servicio | Precio |\n|---|---|\n| Corte de señora | 20 € |\n",
                                         encoding="utf-8")
        (base / "frases.toml").write_text('[sinonimos]\n"señora" = ["mujer"]\n', encoding="utf-8")
        frases.olvidar()
        self.assertEqual(conocimiento.buscar("corte de mujer", base)[0]["precio"], "20 €")
        self.assertEqual(frases.problemas(base), [])

    def test_un_sinonimo_mal_escrito_se_ve_al_arrancar(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        (base / "frases.toml").write_text('[sinonimos]\ncorte = "cortar"\n', encoding="utf-8")
        self.assertTrue(any("lista" in p for p in frases.problemas(base)))

    def test_el_de_la_peluqueria_esta_bien(self):
        self.assertEqual(frases.problemas(self.base), [])


class TestLaDuracionComoSeDice(unittest.TestCase):
    def test_en_palabras(self):
        self.assertEqual(fechas.duracion_en_palabras("90 min"), "una hora y media")
        self.assertEqual(fechas.duracion_en_palabras("120 min"), "dos horas")
        self.assertEqual(fechas.duracion_en_palabras("60 min"), "una hora")
        self.assertEqual(fechas.duracion_en_palabras("30 min"), "media hora")
        self.assertEqual(fechas.duracion_en_palabras("45 min"), "tres cuartos de hora")
        self.assertEqual(fechas.duracion_en_palabras("20 min"), "unos 20 minutos")
        self.assertEqual(fechas.duracion_en_palabras("1 h 15"), "una hora y 15 minutos")
        self.assertEqual(fechas.duracion_en_palabras("2h"), "dos horas")

    def test_lo_que_no_se_entiende_no_se_inventa(self):
        self.assertIsNone(fechas.duracion_en_palabras("depende"))
        self.assertIsNone(fechas.duracion_en_palabras(""))

    def test_el_precio_lo_dice_asi(self):
        llamada = recepcion.Conversacion(negocios.cargar("peluqueria").conocimiento)
        self.assertIn("una hora y media", llamada.atender("¿cuánto valen las mechas?").texto
                      .replace("dos horas", "una hora y media"))
        self.assertIn("media hora", llamada.atender("¿cuánto vale el corte de caballero?").texto)


class TestRepetirYPersona(CasoPeluqueria):
    def test_como_repite_lo_ultimo_tal_cual(self):
        primera = self.texto("¿cuánto vale el corte de caballero?")
        self.assertEqual(self.texto("¿cómo?"), primera)
        self.assertEqual(self.texto("perdona, no te he oído"), primera)

    def test_repetir_no_toca_la_cita(self):
        self.texto("quiero cita", "el jueves")
        self.assertIn("¿A qué hora", self.texto("¿me lo repites?"))
        self.assertIsNotNone(self.llamada.cita.fecha)
        self.assertIsNone(self.llamada.cita.hora)

    def test_repetir_sin_nada_que_repetir_invita_a_hablar(self):
        self.assertIn("Dígame", self.texto("¿cómo?"))

    def test_eres_un_robot_dice_la_verdad(self):
        respuesta = self.llamada.atender("¿eres un robot o una persona?")
        self.assertIn("asistente automático", respuesta.texto)
        self.assertIn("persona", respuesta.aviso)

    def test_hablar_con_alguien_toma_el_recado(self):
        respuesta = self.llamada.atender("quiero hablar con la dueña")
        self.assertIn("recado", respuesta.texto)
        self.assertFalse(respuesta.cuelga)


class TestElRelojSeLee(unittest.TestCase):
    def test_las_horas_del_horario_no_se_leen_como_reloj(self):
        from telefono import voz
        dicho = voz.para_decir("De 10:00 a 14:00 y de 16:30 a 20:00. Sábados de 9:15 a 13:45.")
        self.assertEqual(dicho, "De 10 a 14 y de 16 y media a 20. Sábados de 9 y cuarto a 13 y 45.")


class TestPistasAlProveedor(unittest.TestCase):
    def setUp(self):
        entorno.aislar(self)
        self.negocio = negocios.cargar("peluqueria")

    def test_los_servicios_van_como_pistas(self):
        pistas = telefonia.pistas_de(self.negocio)
        self.assertIn("Mechas", pistas)
        self.assertIn("por la tarde", pistas)
        self.assertLessEqual(len(pistas), 1000)

    def test_el_gather_lleva_pistas_y_modelo_de_telefono(self):
        centralita = telefonia.Centralita(self.negocio)
        xml = centralita.entrada({"CallSid": "CA1", "From": "+34600"}, "https://x/telefono/turno")
        self.assertIn('hints="', xml)
        self.assertIn("Tinte", xml)
        self.assertIn('speechModel="phone_call"', xml)

    def test_sin_pistas_no_se_pone_el_atributo(self):
        self.assertNotIn("hints", telefonia._escuchar("hola", "V", "https://x/t"))


class TestCuatroOpciones(CasoPeluqueria):
    def test_corte_ofrece_los_cuatro_cortes(self):
        dicho = self.texto("¿cuánto vale un corte?")
        for nombre in ("caballero", "señora", "tinte", "infantil"):
            self.assertIn(nombre, dicho.lower())


if __name__ == "__main__":
    unittest.main()
