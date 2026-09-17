"""Pruebas de anular y cambiar una cita, y de no citar en el pasado.

La que más importa es la primera clase. «Quiero anular mi cita del jueves»
lleva la palabra «cita», y antes ganaba la reserva: quien llamaba para anular
colgaba con una cita **nueva**, creyendo que la había quitado. Dos huecos
ocupados y nadie enterado hasta que alguien no aparece.
"""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

from negocio import agenda as ag  # noqa: E402
from negocio import negocio as negocios  # noqa: E402
from mente import recepcion  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
VIERNES = datetime(2026, 9, 11, 10, 0, tzinfo=MADRID)
JUEVES, VIERNES_18 = "2026-09-17", "2026-09-18"


class CasoAnular(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.negocio = negocios.cargar("peluqueria")
        self.agenda = ag.Agenda("peluqueria", self.negocio.horario,
                                ruta=Path(self._tmp.name) / "agenda.json", ahora=VIERNES)

    def reservar(self, fecha=JUEVES, hora="17:00", servicio="Tinte", nombre="Álvaro"):
        return self.agenda.reservar(fecha, hora, 90, servicio, nombre)

    def llamada(self, nombre=None):
        c = recepcion.Conversacion(self.negocio.conocimiento, agenda=self.agenda)
        c.nombre = nombre
        return c

    def guion(self, llamada, *frases):
        texto = ""
        for f in frases:
            texto = llamada.atender(f).texto
        return texto


class TestAnularNoReserva(CasoAnular):
    """La regresión: anular tiene que ganarle a citar."""

    def test_anular_no_deja_una_cita_nueva(self):
        self.reservar()
        dicho = self.guion(self.llamada("Álvaro"), "quiero anular mi cita del jueves")
        self.assertIn("anulo", dicho.lower())
        self.assertNotIn("¿a qué hora", dicho.lower())
        self.assertEqual(self.agenda.citas(), [], "ha quedado una cita en pie")

    def test_las_formas_de_decirlo_que_no_llevan_la_palabra_anular(self):
        for frase in ("no voy a poder ir el jueves", "no puedo ir", "cancela mi cita"):
            with self.subTest(frase=frase):
                self.reservar()
                dicho = self.guion(self.llamada("Álvaro"), frase)
                self.assertIn("anulo", dicho.lower(), dicho)
                self.assertEqual(self.agenda.citas(), [])

    def test_el_hueco_queda_libre_de_verdad(self):
        self.reservar()
        self.guion(self.llamada("Álvaro"), "quiero anular mi cita")
        self.assertIsNone(self.agenda.por_que_no(JUEVES, "17:00", 90))


class TestAQuienSeLeAnula(CasoAnular):
    def test_sin_saber_el_nombre_se_pregunta(self):
        self.reservar()
        llamada = self.llamada()
        self.assertIn("nombre", llamada.atender("quiero anular la cita").texto.lower())
        self.assertIn("anulo", llamada.atender("Álvaro").texto.lower())
        self.assertEqual(self.agenda.citas(), [])

    def test_sin_cita_a_ese_nombre_se_dice_y_no_se_anula_la_de_otro(self):
        self.reservar(nombre="Marta")
        dicho = self.guion(self.llamada("Álvaro"), "quiero anular mi cita")
        self.assertIn("No encuentro", dicho)
        self.assertEqual(len(self.agenda.citas()), 1, "ha anulado la cita de otra persona")

    def test_con_varias_se_pregunta_cual_y_se_quita_solo_esa(self):
        self.reservar(fecha=JUEVES, hora="17:00")
        self.reservar(fecha=VIERNES_18, hora="10:00", servicio="Corte de caballero")
        llamada = self.llamada("Álvaro")
        pregunta = llamada.atender("quiero anular una cita")
        self.assertIn("¿Cuál", pregunta.texto)
        llamada.atender("la del jueves")
        quedan = self.agenda.citas()
        self.assertEqual([c["fecha"] for c in quedan], [VIERNES_18])

    def test_si_dice_el_dia_de_una_de_ellas_no_hace_falta_preguntar(self):
        self.reservar(fecha=JUEVES)
        self.reservar(fecha=VIERNES_18, hora="10:00")
        dicho = self.guion(self.llamada("Álvaro"), "anula la del jueves")
        self.assertIn("anulo", dicho.lower())
        self.assertEqual([c["fecha"] for c in self.agenda.citas()], [VIERNES_18])

    def test_el_dia_de_la_semana_vale_aunque_la_fecha_exacta_sea_otra(self):
        # Hoy es viernes 11. La cita es el viernes 18. «La del viernes»
        # resuelve a hoy, que no tiene cita: hay que encontrarla igual.
        self.reservar(fecha=VIERNES_18, hora="10:00")
        dicho = self.guion(self.llamada("Álvaro"), "anula la del viernes")
        self.assertIn("anulo", dicho.lower())
        self.assertEqual(self.agenda.citas(), [])

    def test_con_dos_del_mismo_dia_de_la_semana_se_pregunta(self):
        # Dos viernes distintos: adivinar cuál sería inventarse la respuesta.
        self.reservar(fecha=VIERNES_18, hora="10:00")
        self.reservar(fecha="2026-09-25", hora="11:00")
        dicho = self.guion(self.llamada("Álvaro"), "anula la del viernes")
        self.assertIn("¿Cuál", dicho)
        self.assertEqual(len(self.agenda.citas()), 2)

    def test_el_nombre_se_busca_sin_tildes(self):
        # Whisper escribe «Alvaro» o «Álvaro» según le da.
        self.reservar(nombre="Álvaro")
        self.guion(self.llamada("Alvaro"), "quiero anular mi cita")
        self.assertEqual(self.agenda.citas(), [])

    def test_no_se_anulan_citas_pasadas(self):
        # Se escribe a mano: `reservar` ya no deja apuntar en el pasado, y lo
        # que se prueba aquí es que una cita vieja del fichero no se toque.
        self.agenda._guardar([{"id": 1, "fecha": "2026-09-08", "hora": "10:00",
                               "duracion": 30, "servicio": "Corte de caballero",
                               "nombre": "Álvaro", "creada": "2026-09-01 10:00"}])
        dicho = self.guion(self.llamada("Álvaro"), "quiero anular mi cita")
        self.assertIn("No encuentro", dicho)
        self.assertEqual(len(self.agenda.citas()), 1)


class TestCambiarLaCita(CasoAnular):
    def test_anula_la_vieja_y_pide_el_dia_de_la_nueva(self):
        self.reservar()
        dicho = self.guion(self.llamada("Álvaro"), "quería cambiar la cita del jueves")
        self.assertIn("anulo", dicho.lower())
        self.assertIn("día", dicho.lower())
        self.assertEqual(self.agenda.citas(), [])

    def test_la_nueva_conserva_el_servicio_y_el_nombre(self):
        self.reservar(servicio="Mechas")
        llamada = self.llamada("Álvaro")
        self.guion(llamada, "quiero cambiar la cita", "el viernes", "a las once")
        self.assertEqual(llamada.cita.servicio, "Mechas")
        self.assertEqual(llamada.cita.nombre, "Álvaro")
        self.assertEqual([c["servicio"] for c in self.agenda.citas()], ["Mechas"])


class TestSinAgenda(CasoAnular):
    def test_sin_agenda_se_toma_nota_de_la_anulacion(self):
        llamada = recepcion.Conversacion(self.negocio.conocimiento)   # sin agenda
        respuesta = llamada.atender("quiero anular mi cita del jueves")
        self.assertIn("Tomo nota", respuesta.texto)
        self.assertEqual(respuesta.tipo_aviso, "cita")


class TestNoSeCitaEnElPasado(CasoAnular):
    """Alguien llama a las doce y dice «a las diez»: esa hora ya no existe."""

    def a_las(self, hora_reloj, minuto=0):
        self.agenda = ag.Agenda("peluqueria", self.negocio.horario,
                                ruta=Path(self._tmp.name) / "agenda.json",
                                ahora=datetime(2026, 9, 15, hora_reloj, minuto, tzinfo=MADRID))
        return self.llamada()

    def test_una_hora_de_esta_manana_se_rechaza_y_se_ofrece_lo_que_queda_hoy(self):
        dicho = self.guion(self.a_las(12, 30), "cita para un corte de caballero",
                           "hoy", "a las diez de la mañana")
        self.assertIn("ya ha pasado", dicho)
        self.assertIn("una de la tarde", dicho)     # lo que queda de hoy
        self.assertEqual(self.agenda.citas(), [])

    def test_si_el_dia_se_acabo_se_ofrecen_los_siguientes(self):
        dicho = self.guion(self.a_las(21), "cita para un tinte",
                           "hoy", "a las once de la mañana")
        self.assertIn("ya ha pasado", dicho)
        # El día siguiente se dice «mañana», no «el miércoles 16»: es lo que
        # diría una persona. Esto esperaba el nombre del día, y pasaba solo
        # porque `Hueco.dicho` miraba el reloj del sistema en vez del de la
        # agenda —con el reloj de verdad el miércoles 16 ya no era mañana—.
        self.assertIn("queda mañana", dicho)
        self.assertNotIn("hoy", dicho)          # el día que se acabó, no se ofrece
        self.assertEqual(self.agenda.citas(), [])

    def test_la_agenda_no_reserva_en_el_pasado_ni_pidiendoselo(self):
        agenda = ag.Agenda("peluqueria", self.negocio.horario,
                           ruta=Path(self._tmp.name) / "otra.json",
                           ahora=datetime(2026, 9, 15, 12, 30, tzinfo=MADRID))
        self.assertEqual(agenda.por_que_no("2026-09-15", "10:00", 30), "pasado")
        with self.assertRaises(ValueError) as caso:
            agenda.reservar("2026-09-15", "10:00", 30, "Corte de caballero", "Marta")
        self.assertEqual(str(caso.exception), "pasado")

    def test_los_huecos_de_hoy_empiezan_en_el_reloj_no_en_la_apertura(self):
        agenda = ag.Agenda("peluqueria", self.negocio.horario,
                           ruta=Path(self._tmp.name) / "otra.json",
                           ahora=datetime(2026, 9, 15, 12, 30, tzinfo=MADRID))
        # A las 12:30 en punto, el hueco de las 12:30 ya no se ofrece: la
        # agenda lo daría por pasado al reservarlo, y un hueco que se ofrece
        # y no se puede coger es peor que no ofrecerlo.
        self.assertEqual([h.hora for h in agenda.huecos("2026-09-15", 30)],
                         ["13:00", "13:30", "16:30"])


class TestUnSoloReloj(CasoAnular):
    """La conversación y la agenda tienen que estar en el mismo día."""

    def test_hoy_significa_lo_mismo_en_las_dos(self):
        llamada = self.llamada()
        self.assertEqual(llamada.ahora(), self.agenda.ahora())
        llamada.atender("quiero cita")
        llamada.atender("hoy")
        self.assertEqual(llamada.cita.fecha, "2026-09-11")   # el del reloj de la agenda

    def test_sin_agenda_se_usa_el_reloj_de_madrid(self):
        llamada = recepcion.Conversacion(self.negocio.conocimiento)
        self.assertEqual(str(llamada.ahora().tzinfo), "Europe/Madrid")


class TestDejaDeRepetirse(CasoAnular):
    def test_a_la_tercera_sin_entender_se_toma_el_recado(self):
        llamada = self.llamada()
        primera = llamada.atender("aaaa bbbb").texto
        segunda = llamada.atender("cccc dddd").texto
        tercera = llamada.atender("eeee ffff").texto
        self.assertEqual(primera, segunda)
        self.assertNotEqual(tercera, segunda)
        self.assertIn("no acabo de entenderle", tercera)

    def test_entender_algo_por_medio_reinicia_la_cuenta(self):
        llamada = self.llamada()
        llamada.atender("aaaa bbbb")
        llamada.atender("cccc dddd")
        llamada.atender("¿qué horario tenéis?")          # esto sí se entiende
        self.assertNotIn("no acabo de entenderle", llamada.atender("eeee ffff").texto)


if __name__ == "__main__":
    unittest.main()


class TestPreguntarPorLaCitaDeUno(CasoAnular):
    """«¿Tengo yo cita mañana?» abría una cita nueva: quien llamaba a
    confirmar colgaba con dos. Es de las llamadas más comunes que hay."""

    def test_se_le_dice_cual_es(self):
        self.reservar(nombre="Marta")
        dicho = self.guion(self.llamada("Marta"), "¿tengo yo cita para mañana?")
        self.assertIn("tiene cita de tinte", dicho)
        self.assertIn("cinco de la tarde", dicho)
        self.assertEqual(len(self.agenda.citas()), 1, "no puede abrir otra")

    def test_si_no_se_sabe_quien_es_se_pregunta(self):
        self.reservar(nombre="Marta")
        llamada = self.llamada()
        self.assertIn("¿A nombre de quién", llamada.atender("¿tengo cita?").texto)
        self.assertIn("tiene cita", llamada.atender("Marta").texto)

    def test_con_varias_se_dicen_todas(self):
        self.reservar(nombre="Marta")
        self.reservar(fecha=VIERNES_18, hora="11:00", nombre="Marta")
        dicho = self.guion(self.llamada("Marta"), "¿cuándo tengo cita?")
        self.assertIn(" o ", dicho)
        self.assertIn("once de la mañana", dicho)

    def test_sin_cita_a_ese_nombre_se_dice(self):
        self.reservar(nombre="Marta")
        dicho = self.guion(self.llamada("Pepe"), "¿tengo yo cita?")
        self.assertIn("No encuentro ninguna cita", dicho)

    def test_sin_agenda_se_toma_nota(self):
        llamada = recepcion.Conversacion(self.negocio.conocimiento)
        self.assertIn("Tomo nota", llamada.atender("¿tengo yo cita mañana?").texto)


class TestMoverLaCita(CasoAnular):
    def test_mover_mi_cita_anula_la_vieja_y_abre_la_nueva(self):
        self.reservar(nombre="Marta")
        llamada = self.llamada("Marta")
        dicho = llamada.atender("quería mover mi cita").texto
        self.assertIn("anulo", dicho.lower())
        self.assertIn("¿Qué día", dicho)
        self.assertEqual(self.agenda.citas(), [], "la vieja se ha quitado")

    def test_y_la_nueva_conserva_el_servicio(self):
        self.reservar(nombre="Marta")
        llamada = self.llamada("Marta")
        self.guion(llamada, "quiero moverla", "el viernes 18", "a las once", "sí")
        citas = self.agenda.citas()
        self.assertEqual(len(citas), 1)
        self.assertEqual(citas[0]["servicio"], "Tinte")

    def test_las_formas_de_decirlo(self):
        # Una hora distinta por frase: si no, la segunda reserva choca con la
        # primera y el fallo parece de la frase y es de la prueba.
        formas = [("quería mover mi cita", "10:00"),
                  ("¿me la puedes adelantar?", "11:30"),
                  ("necesito cambiar de hora", "16:30"),
                  ("quiero retrasarla", "18:00")]
        for frase, hora in formas:
            with self.subTest(frase=frase):
                self.reservar(hora=hora, nombre="Marta")
                dicho = self.guion(self.llamada("Marta"), frase)
                self.assertIn("anulo", dicho.lower(), frase)
