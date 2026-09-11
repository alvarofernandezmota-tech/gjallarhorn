"""Pruebas de las horas como se dicen por teléfono, y de los huecos que se ofrecen.

Por teclado se escribe «a las 17:30». Por teléfono se dice «las cinco y
media», «sobre las cinco», «el de las once», «las cinco menos cuarto»… y
quien transcribe escribe «a las 5:30», que **no** son las cinco y media de la
madrugada aunque lleve minutos.

Y a «¿a qué hora?» mucha gente contesta «cuando podáis»: se le dicen los
huecos, no se le repite la pregunta.
"""

import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

from negocio import agenda as ag  # noqa: E402
from mente import fechas  # noqa: E402
from negocio import negocio as negocios  # noqa: E402
from mente import recepcion  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
VIERNES = datetime(2026, 9, 11, 10, 0, tzinfo=MADRID)
JUEVES = "2026-09-17"


class TestLaHoraComoSeDice(unittest.TestCase):
    def hora(self, frase):
        encontrado = fechas.interpretar(f"el jueves {frase}", VIERNES)
        return (encontrado[1], encontrado[2]) if encontrado else None

    def test_menos_cuarto_y_y_veinte(self):
        self.assertEqual(self.hora("a las cinco menos cuarto"), ("04:45", False))
        self.assertEqual(self.hora("a las cinco y veinte"), ("05:20", False))
        self.assertEqual(self.hora("a las seis menos diez de la tarde"), ("17:50", True))

    def test_la_una_menos_cuarto_son_las_doce_y_cuarenta_y_cinco(self):
        self.assertEqual(self.hora("a la una menos cuarto"), ("12:45", True))

    def test_sobre_las_hacia_las_a_eso_de_las(self):
        self.assertEqual(self.hora("sobre las cinco de la tarde"), ("17:00", True))
        self.assertEqual(self.hora("hacia las diez"), ("10:00", False))
        self.assertEqual(self.hora("a eso de las diez"), ("10:00", False))

    def test_a_las_cinco_y_media_transcrito_con_numeros_no_esta_acotado(self):
        # Quien transcribe escribe «a las 5:30»; son las cinco y media, y no
        # se sabe si de la mañana. Antes se daba por acotado y se citaba a
        # alguien a las 05:30.
        self.assertEqual(self.hora("a las 5:30"), ("05:30", False))
        self.assertEqual(self.hora("a las 17:30"), ("17:30", True))

    def test_diecisiete_horas(self):
        self.assertEqual(self.hora("a las 17 horas"), ("17:00", True))
        self.assertEqual(self.hora("a las 17h"), ("17:00", True))

    def test_una_hora_imposible_no_es_una_hora(self):
        self.assertEqual(self.hora("a las 25"), (None, False))

    def test_manana_por_la_manana_es_el_dia_siguiente(self):
        # Lleva «mañana» dos veces: la primera es el día, la segunda la franja.
        # Antes la franja tapaba al día y no se entendía ninguna fecha.
        fecha, hora, _, _ = fechas.interpretar("hueco mañana por la mañana", VIERNES)
        self.assertEqual((fecha, hora), ("2026-09-12", None))
        self.assertEqual(fechas.franja_en("mañana por la mañana"), "manana")
        self.assertIsNone(fechas.interpretar("el sábado por la mañana", VIERNES)[1])

    def test_esta_tarde_es_hoy(self):
        fecha, hora, acotada, _ = fechas.interpretar("esta tarde a las seis", VIERNES)
        self.assertEqual((fecha, hora, acotada), ("2026-09-11", "18:00", True))

    def test_el_dia_tres(self):
        self.assertEqual(fechas.interpretar("el día 3", VIERNES)[0], "2026-10-03")


class TestLaHoraSuelta(unittest.TestCase):
    """Contestando a «¿a qué hora?», casi nadie dice «a las»."""

    def test_sin_a_las(self):
        self.assertEqual(fechas.hora_suelta("las cinco"), ("05:00", False))
        self.assertEqual(fechas.hora_suelta("cinco y media"), ("05:30", False))
        self.assertEqual(fechas.hora_suelta("las 11"), ("11:00", False))
        self.assertEqual(fechas.hora_suelta("el de las once"), ("11:00", False))

    def test_con_muletillas_alrededor(self):
        self.assertEqual(fechas.hora_suelta("sobre las diez, mejor"), ("10:00", False))
        self.assertEqual(fechas.hora_suelta("pues las cinco de la tarde"), ("17:00", True))
        self.assertEqual(fechas.hora_suelta("las seis y media si puede ser"), ("06:30", False))

    def test_una_frase_con_un_numero_dentro_no_es_una_hora(self):
        self.assertIsNone(fechas.hora_suelta("para dos personas"))
        self.assertIsNone(fechas.hora_suelta("somos tres"))

    def test_las_cinco_menos_cuarto(self):
        self.assertEqual(fechas.hora_suelta("las cinco menos cuarto"), ("04:45", False))


class TestDecirLaHora(unittest.TestCase):
    def test_menos_cuarto_se_dice_menos_cuarto(self):
        self.assertEqual(fechas.hora_en_palabras("16:45"), "las cinco menos cuarto de la tarde")
        self.assertEqual(fechas.hora_en_palabras("12:45"), "la una menos cuarto de la tarde")
        self.assertEqual(fechas.hora_en_palabras("11:45"), "las doce menos cuarto del mediodía")

    def test_lo_de_siempre_sigue_igual(self):
        self.assertEqual(fechas.hora_en_palabras("17:30"), "las cinco y media de la tarde")
        self.assertEqual(fechas.hora_en_palabras("10:15"), "las diez y cuarto de la mañana")


class CasoHuecos(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.negocio = negocios.cargar("peluqueria")
        self.agenda = ag.Agenda("peluqueria", self.negocio.horario,
                                ruta=Path(self._tmp.name) / "agenda.json", ahora=VIERNES)
        self.llamada = recepcion.Conversacion(self.negocio.conocimiento, agenda=self.agenda)

    def texto(self, *frases):
        texto = ""
        for frase in frases:
            texto = self.llamada.atender(frase).texto
        return texto

    def cita(self):
        return self.llamada.cita


class TestSeOfrecenHuecos(CasoHuecos):
    def test_tienes_hueco_el_jueves_se_contesta_con_los_huecos(self):
        dicho = self.texto("¿tenéis hueco el jueves?", "un corte de caballero")
        self.assertIn("El jueves 17 tengo", dicho)
        self.assertIn("las diez de la mañana", dicho)
        self.assertIn("¿Cuál le viene bien?", dicho)

    def test_por_la_tarde_da_los_de_la_tarde(self):
        dicho = self.texto("¿tenéis hueco el jueves por la tarde?", "un corte de caballero")
        self.assertIn("cuatro y media de la tarde", dicho)
        self.assertNotIn("mañana", dicho)

    def test_por_la_manana_da_los_de_la_manana(self):
        dicho = self.texto("¿tenéis algo el jueves por la mañana?", "un corte de caballero")
        self.assertIn("de la mañana", dicho)
        self.assertNotIn("tarde", dicho)

    def test_cuando_podais_al_preguntar_la_hora(self):
        dicho = self.texto("quiero cita de tinte", "el jueves", "cuando podáis")
        self.assertIn("El jueves 17 tengo", dicho)

    def test_cuando_podais_sin_dia_da_lo_mas_pronto(self):
        dicho = self.texto("quiero cita para un tinte, cuando podáis")
        self.assertIn("Lo más pronto que tengo", dicho)
        self.assertIn("hoy", dicho)

    def test_pedir_cita_normal_sigue_preguntando_la_hora(self):
        self.assertIn("¿A qué hora", self.texto("quiero cita de tinte el jueves"))

    def test_sin_agenda_no_se_ofrece_nada(self):
        llamada = recepcion.Conversacion(self.negocio.conocimiento)
        llamada.atender("¿tenéis hueco el jueves?")
        self.assertIn("¿A qué hora", llamada.atender("un tinte").texto)

    def test_un_dia_lleno_ofrece_los_siguientes(self):
        for hora, cuanto in (("10:00", 120), ("12:00", 120), ("16:30", 120), ("18:30", 90)):
            self.agenda.reservar(JUEVES, hora, cuanto, "Mechas", "Alguien")
        # Con el día entero cogido, da igual de qué sea: no cabe nada.
        dicho = self.texto("¿tenéis hueco el jueves?", "un corte de caballero")
        self.assertIn("El jueves 17 no me queda", dicho)
        self.assertIn("el viernes 18", dicho)


class TestElegirElHuecoOfrecido(CasoHuecos):
    def test_si_con_uno_solo_lo_coge(self):
        for hora in ("10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30",
                     "16:30", "17:00", "17:30", "18:00", "18:30", "19:00"):
            self.agenda.reservar(JUEVES, hora, 30, "Corte", "Alguien")
        dicho = self.texto("¿tenéis hueco el jueves?", "un corte de caballero")
        self.assertIn("las siete y media de la tarde", dicho)
        self.texto("sí")
        self.assertEqual((self.cita().hora, self.cita().acotada), ("19:30", True))

    def test_si_con_varios_pregunta_cual(self):
        self.texto("¿tenéis hueco el jueves?", "un corte de caballero")
        self.assertIn("¿Cuál de ellos", self.texto("sí"))
        self.assertIsNone(self.cita().hora)

    def test_el_primero_y_el_ultimo(self):
        self.texto("¿tenéis hueco el jueves por la tarde?", "un corte de caballero", "el último")
        self.assertEqual(self.cita().hora, "17:30")
        otra = recepcion.Conversacion(self.negocio.conocimiento, agenda=self.agenda)
        otra.atender("¿tenéis hueco el jueves por la tarde?")
        otra.atender("un corte de caballero")
        otra.atender("el primero")
        self.assertEqual(otra.cita.hora, "16:30")

    def test_decir_la_hora_ofrecida_ya_esta_acotada(self):
        self.texto("¿tenéis hueco el jueves por la tarde?", "un corte de caballero", "las cinco")
        self.assertEqual((self.cita().hora, self.cita().acotada), ("17:00", True))

    def test_decir_el_dia_ofrecido_coge_su_hora(self):
        dicho = self.texto("quiero cita de tinte el lunes a las cinco de la tarde")
        self.assertIn("cerrados", dicho)
        self.assertIn("el martes 15", dicho)
        dicho = self.texto("el martes")
        self.assertEqual((self.cita().fecha, self.cita().hora), ("2026-09-15", "10:00"))
        self.assertIn("¿A nombre de quién", dicho)

    def test_si_pero_con_otra_hora_manda_la_hora(self):
        for hora in ("10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30",
                     "16:30", "17:00", "17:30", "18:00", "18:30", "19:00"):
            self.agenda.reservar(JUEVES, hora, 30, "Corte", "Alguien")
        self.texto("¿tenéis hueco el jueves?", "un corte de caballero")          # solo queda las 19:30
        dicho = self.texto("sí, a las siete de la tarde")
        # Lo que dijo manda: las siete estan cogidas, y se le dice, en vez de
        # apuntarle a las siete y media por el «sí».
        self.assertIn("ya tengo a alguien", dicho)
        self.assertIsNone(self.cita().hora)

    def test_otra_hora_distinta_se_respeta(self):
        self.texto("¿tenéis hueco el jueves por la tarde?", "un corte de caballero", "a las seis de la tarde")
        self.assertEqual(self.cita().hora, "18:00")


class TestAgendaHuecosHasta(unittest.TestCase):
    def test_hasta_acota_por_arriba(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        negocio = negocios.cargar("peluqueria")
        agenda = ag.Agenda("peluqueria", negocio.horario, ruta=Path(tmp.name) / "a.json", ahora=VIERNES)
        huecos = agenda.huecos(JUEVES, 30, desde=13 * 60, hasta=14 * 60, tope=10)
        self.assertEqual([h.hora for h in huecos], ["13:00", "13:30"])


if __name__ == "__main__":
    unittest.main()


class TestEstaAbiertoAhora(unittest.TestCase):
    """«¿Está abierto ahora?» quiere un sí o un no.

    Recitar los siete días para que quien llama traduzca es lo que hacía
    antes, y es justo lo que no hace una persona: con el horario escrito y
    un reloj, se sabe.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.negocio = negocios.cargar("peluqueria")

    def preguntar(self, cuando, frase="¿estáis abiertos ahora?"):
        agenda = ag.Agenda("peluqueria", self.negocio.horario,
                           ruta=Path(self._tmp.name) / "a.json", ahora=cuando)
        llamada = recepcion.Conversacion(self.negocio.conocimiento, agenda=agenda)
        return llamada.atender(frase).texto

    def test_abierto_dice_hasta_cuando(self):
        dicho = self.preguntar(datetime(2026, 9, 15, 11, 0, tzinfo=MADRID))
        self.assertIn("Sí", dicho)
        self.assertIn("hasta las dos de la tarde", dicho)

    def test_en_la_pausa_del_mediodia_dice_cuando_vuelve(self):
        dicho = self.preguntar(datetime(2026, 9, 15, 15, 0, tzinfo=MADRID))
        self.assertIn("cerrado", dicho)
        self.assertIn("hoy a las cuatro y media de la tarde", dicho)

    def test_despues_de_cerrar_dice_mañana(self):
        dicho = self.preguntar(datetime(2026, 9, 15, 21, 0, tzinfo=MADRID))
        self.assertIn("mañana a las diez de la mañana", dicho)

    def test_un_dia_cerrado_entero(self):
        dicho = self.preguntar(datetime(2026, 9, 14, 11, 0, tzinfo=MADRID))   # lunes
        self.assertIn("cerrado", dicho)
        self.assertIn("mañana", dicho)

    def test_sin_ahora_se_sigue_diciendo_el_horario_entero(self):
        dicho = self.preguntar(datetime(2026, 9, 15, 11, 0, tzinfo=MADRID),
                               "¿qué horario tenéis?")
        self.assertIn("martes a viernes", dicho)

    def test_sin_agenda_no_se_inventa_un_reloj(self):
        llamada = recepcion.Conversacion(self.negocio.conocimiento)
        self.assertIn("martes a viernes", llamada.atender("¿estáis abiertos ahora?").texto)


class TestElHorarioSabeLaHora(unittest.TestCase):
    def setUp(self):
        self.horario = negocios.cargar("peluqueria").horario

    def test_el_tramo_en_el_que_cae_un_minuto(self):
        martes = date(2026, 9, 15)
        self.assertEqual(self.horario.tramo_de(martes, 11 * 60), (10 * 60, 14 * 60))
        self.assertIsNone(self.horario.tramo_de(martes, 15 * 60))
        # El minuto en el que cierra ya es «cerrado», no «abierto».
        self.assertIsNone(self.horario.tramo_de(martes, 14 * 60))

    def test_cuando_vuelve_a_abrir(self):
        martes = date(2026, 9, 15)
        self.assertEqual(self.horario.proxima_apertura(martes, 15 * 60),
                         (martes, 16 * 60 + 30))
        self.assertEqual(self.horario.proxima_apertura(martes, 21 * 60),
                         (date(2026, 9, 16), 10 * 60))
        # Domingo por la noche: lo siguiente es el martes, porque el lunes cierra.
        self.assertEqual(self.horario.proxima_apertura(date(2026, 9, 13), 22 * 60),
                         (date(2026, 9, 15), 10 * 60))

    def test_un_negocio_que_no_abre_nunca_no_promete_nada(self):
        from negocio import agenda
        cerrado = agenda.Horario.desde({"lunes": [], "martes": []})
        self.assertIsNone(cerrado.proxima_apertura(date(2026, 9, 15), 0))
