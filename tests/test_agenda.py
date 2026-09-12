"""Pruebas de agenda.py — reservar de verdad, no prometer que alguien confirmará.

Lo que se vigila: que no se meta a dos personas en el mismo sillón, que no se
cite a nadie con el negocio cerrado, y que un servicio de 90 minutos ocupe 90
minutos y no «una hora».
"""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

# La raiz del repo **es** el paquete `hugin`, asi que lo que tiene que
# estar en el sys.path es la carpeta que lo contiene.
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ.parent))

import entorno  # noqa: E402,F401

from hugin.negocio import agenda  # noqa: E402
from hugin.negocio import negocio as negocios  # noqa: E402
from hugin.mente import recepcion  # noqa: E402

from zoneinfo import ZoneInfo  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")

HORARIO = agenda.Horario.desde({
    "lunes": [],
    "martes": ["10:00-14:00", "16:30-20:00"],
    "jueves": ["10:00-14:00", "16:30-20:00"],
    "sabado": ["09:00-14:00"],
})
LUNES, MARTES, JUEVES = "2026-09-14", "2026-09-15", "2026-09-17"


class CasoAgenda(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.agenda = agenda.Agenda("prueba", HORARIO,
                                    ruta=Path(self._tmp.name) / "agenda.json")


class TestElHorario(unittest.TestCase):
    def test_un_dia_sin_tramos_esta_cerrado(self):
        self.assertFalse(HORARIO.abre(agenda.date.fromisoformat(LUNES)))
        self.assertTrue(HORARIO.abre(agenda.date.fromisoformat(MARTES)))

    def test_un_dia_que_no_esta_escrito_esta_cerrado(self):
        # El miércoles no aparece en el horario: cerrado, no «abierto por defecto».
        self.assertFalse(HORARIO.abre(agenda.date.fromisoformat("2026-09-16")))

    def test_un_servicio_tiene_que_caber_entero_en_el_tramo(self):
        dia = agenda.date.fromisoformat(MARTES)
        self.assertTrue(HORARIO.cabe(dia, 13 * 60, 60))       # 13:00–14:00
        self.assertFalse(HORARIO.cabe(dia, 13 * 60 + 30, 60))  # 13:30–14:30: se sale

    def test_un_horario_mal_escrito_se_explica(self):
        with self.assertRaises(ValueError) as caso:
            agenda.Horario.desde({"martes": ["10-14"]})
        self.assertIn("HH:MM-HH:MM", str(caso.exception))
        with self.assertRaises(ValueError):
            agenda.Horario.desde({"marte": ["10:00-14:00"]})
        with self.assertRaises(ValueError):
            agenda.Horario.desde({"martes": ["14:00-10:00"]})

    def test_sin_horario_no_hay_agenda(self):
        self.assertIsNone(agenda.Horario.desde(None))
        self.assertIsNone(agenda.Horario.desde({}))


class TestLaDuracion(unittest.TestCase):
    def test_formatos_de_la_tabla(self):
        self.assertEqual(agenda.duracion_en_minutos("90 min"), 90)
        self.assertEqual(agenda.duracion_en_minutos("1 h"), 60)
        self.assertEqual(agenda.duracion_en_minutos("1h30"), 90)
        self.assertEqual(agenda.duracion_en_minutos("2 horas"), 120)

    def test_sin_duracion_se_reserva_el_defecto(self):
        # Mejor pasarse que meter a dos personas en el mismo sillón.
        self.assertEqual(agenda.duracion_en_minutos(None), agenda.DURACION_POR_DEFECTO)
        self.assertEqual(agenda.duracion_en_minutos(""), agenda.DURACION_POR_DEFECTO)


class TestPorQueNo(CasoAgenda):
    def test_cerrado(self):
        self.assertEqual(self.agenda.por_que_no(LUNES, "10:00", 30), "cerrado")

    def test_fuera_de_horario(self):
        self.assertEqual(self.agenda.por_que_no(MARTES, "15:00", 30), "fuera")
        self.assertEqual(self.agenda.por_que_no(MARTES, "05:00", 30), "fuera")

    def test_cabe(self):
        self.assertIsNone(self.agenda.por_que_no(MARTES, "10:00", 30))

    def test_ocupado_es_pisarse_en_minutos_no_empezar_a_la_misma_hora(self):
        # Un tinte de 90 min a las 10:00 ocupa hasta las 11:30.
        self.agenda.reservar(MARTES, "10:00", 90, "Tinte", "Álvaro")
        self.assertEqual(self.agenda.por_que_no(MARTES, "11:00", 30), "ocupado")
        self.assertIsNone(self.agenda.por_que_no(MARTES, "11:30", 30))

    def test_reservar_vuelve_a_comprobar(self):
        # Entre la pregunta y la reserva puede haber entrado otra llamada.
        self.agenda.reservar(MARTES, "10:00", 30, "Corte", "Marta")
        with self.assertRaises(ValueError) as caso:
            self.agenda.reservar(MARTES, "10:00", 30, "Corte", "Pepe")
        self.assertEqual(str(caso.exception), "ocupado")
        self.assertEqual(len(self.agenda.citas(MARTES)), 1)


class TestLosHuecos(CasoAgenda):
    def test_los_huecos_de_un_dia_respetan_lo_reservado(self):
        self.agenda.reservar(MARTES, "10:00", 90, "Tinte", "Álvaro")
        horas = [h.hora for h in self.agenda.huecos(MARTES, 30)]
        self.assertEqual(horas, ["11:30", "12:00", "12:30"])

    def test_desde_una_hora_da_los_de_despues(self):
        horas = [h.hora for h in self.agenda.huecos(MARTES, 30, desde=17 * 60)]
        self.assertEqual(horas, ["17:00", "17:30", "18:00"])

    def test_un_servicio_largo_no_cabe_al_final_del_tramo(self):
        horas = [h.hora for h in self.agenda.huecos(MARTES, 120, desde=12 * 60)]
        self.assertEqual(horas[0], "12:00")           # 12–14 cabe
        self.assertNotIn("12:30", horas)               # 12:30–14:30 no

    def test_los_proximos_huecos_saltan_los_dias_cerrados(self):
        huecos = self.agenda.proximos_huecos(LUNES, 30, por_dia=1)
        self.assertEqual([h.fecha for h in huecos], [MARTES, JUEVES, "2026-09-19"])

    def test_los_huecos_se_dicen_como_una_persona(self):
        hueco = self.agenda.proximos_huecos(LUNES, 30)[0]
        self.assertIn("martes", hueco.dicho)
        self.assertIn("diez de la mañana", hueco.dicho)


class TestLaConversacionReserva(unittest.TestCase):
    """La agenda dentro de la llamada: lo que oye quien llama."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.negocio = negocios.cargar("peluqueria")
        self.agenda = agenda.Agenda("peluqueria", self.negocio.horario,
                                    ruta=Path(self._tmp.name) / "agenda.json")

    def llamada(self):
        return recepcion.Conversacion(self.negocio.conocimiento, agenda=self.agenda)

    def decir(self, llamada, *frases):
        texto = ""
        for f in frases:
            texto = llamada.atender(f).texto
        return texto

    def test_reserva_de_verdad_y_lo_dice(self):
        dicho = self.decir(self.llamada(), "cita para un tinte", "el jueves",
                           "a las cinco de la tarde", "Álvaro")
        self.assertIn("Reservada", dicho)
        self.assertEqual(len(self.agenda.citas(JUEVES)), 1)

    def test_con_el_negocio_cerrado_ofrece_otros_dias_antes_de_pedir_el_nombre(self):
        dicho = self.decir(self.llamada(), "cita para un tinte", "el lunes",
                           "a las cinco de la tarde")
        self.assertIn("cerrados", dicho)
        self.assertIn("martes", dicho)
        self.assertNotIn("nombre", dicho.lower())

    def test_con_el_hueco_cogido_ofrece_horas_cercanas(self):
        self.agenda.reservar(JUEVES, "17:00", 90, "Tinte", "Álvaro")
        dicho = self.decir(self.llamada(), "cita para un corte de caballero",
                           "el jueves", "a las seis de la tarde")
        self.assertIn("ya tengo a alguien", dicho)
        self.assertIn("seis y media de la tarde", dicho)   # la más cercana, no la mañana

    def test_la_hora_ambigua_la_resuelve_el_horario(self):
        # «A las once» un jueves: las 23:00 no existen, así que son las 11:00
        # y no se pregunta. Pero «a las cinco» sin agenda SÍ se pregunta, y
        # eso lo cubre test_conversacion.
        dicho = self.decir(self.llamada(), "cita para un corte de caballero",
                           "el jueves", "a las once")
        self.assertIn("nombre", dicho.lower())

    def test_dos_llamadas_no_pueden_coger_el_mismo_hueco(self):
        self.decir(self.llamada(), "cita para un corte de caballero", "el jueves",
                   "a las diez de la mañana", "Marta")
        dicho = self.decir(self.llamada(), "cita para un corte de caballero", "el jueves",
                           "a las diez de la mañana")
        self.assertIn("ya tengo a alguien", dicho)
        self.assertEqual(len(self.agenda.citas(JUEVES)), 1)

    def test_sin_agenda_sigue_tomando_nota(self):
        llamada = recepcion.Conversacion(self.negocio.conocimiento)   # sin agenda
        dicho = self.decir(llamada, "cita para un tinte", "el lunes",
                           "a las cinco de la tarde", "Álvaro")
        self.assertIn("confirmamos", dicho)
        self.assertEqual(self.agenda.citas(), [])


if __name__ == "__main__":
    unittest.main()


class TestUnHuecoOfrecidoSePuedeCoger(unittest.TestCase):
    """Salió solo: la prueba del panel reservó el primer hueco del día y la
    agenda lo rechazó por «pasado». Era el minuto justo en el que estábamos."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.negocio = negocios.cargar("peluqueria")

    def agenda_a_las(self, hora, minuto):
        ahora = datetime(2026, 9, 15, hora, minuto, tzinfo=MADRID)   # martes
        return agenda.Agenda("peluqueria", self.negocio.horario,
                         ruta=Path(self._tmp.name) / "a.json", ahora=ahora)

    def test_el_hueco_del_minuto_en_punto_no_se_ofrece(self):
        agenda = self.agenda_a_las(10, 0)
        self.assertNotIn("10:00", [h.hora for h in agenda.huecos("2026-09-15", 30, tope=9)])

    def test_todos_los_que_ofrece_se_pueden_reservar(self):
        for minuto in (0, 1, 29, 30, 31):
            with self.subTest(minuto=minuto):
                agenda = self.agenda_a_las(10, minuto)
                for hueco in agenda.huecos("2026-09-15", 30, tope=3):
                    self.assertIsNone(agenda.por_que_no(hueco.fecha, hueco.hora, 30),
                                      f"ofrecido y no reservable: {hueco.hora}")
