"""Pruebas de fechas.py — cuándo quiere la cita quien llama.

Dos propiedades por encima de las demás, y las dos salieron de fallos reales:

1. **Siempre hacia delante.** Nadie reserva para el martes pasado. Un parser
   de diario hace lo contrario, y por eso este es propio.
2. **Una hora sin acotar se marca como tal.** «A las cinco» no se convierte en
   las 17:00 por su cuenta: devuelve 05:00 y avisa de que nadie dijo si era
   mañana o tarde. Confirmarla es del recepcionista, preguntando.
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

from mente import fechas  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
# Viernes 11 de septiembre de 2026, por la mañana.
VIERNES = datetime(2026, 9, 11, 10, 0, tzinfo=MADRID)


class CasoFechas(unittest.TestCase):
    def leer(self, frase, ahora=VIERNES):
        return fechas.interpretar(frase, ahora)


class TestSiempreHaciaDelante(CasoFechas):
    def test_el_lunes_es_el_que_viene_no_el_que_paso(self):
        # Hoy es viernes. El lunes que importa es el 14, no el 7.
        self.assertEqual(self.leer("cita el lunes")[0], "2026-09-14")

    def test_el_mismo_dia_de_la_semana_es_hoy(self):
        # Un viernes por la mañana, «el viernes» lo normal es que sea hoy. El
        # recepcionista pregunta la hora igual, así que se ve enseguida.
        self.assertEqual(self.leer("cita el viernes")[0], "2026-09-11")

    def test_que_viene_salta_a_la_semana_siguiente(self):
        self.assertEqual(self.leer("cita el viernes que viene")[0], "2026-09-18")

    def test_manana_y_pasado_manana(self):
        self.assertEqual(self.leer("cita mañana")[0], "2026-09-12")
        self.assertEqual(self.leer("cita pasado mañana")[0], "2026-09-13")

    def test_hoy_es_hoy(self):
        self.assertEqual(self.leer("hueco hoy")[0], "2026-09-11")

    def test_un_dia_del_mes_que_ya_paso_es_del_mes_siguiente(self):
        # Hoy es 11. «El 3» no es el 3 de este mes: nadie pide cita para ayer.
        self.assertEqual(self.leer("cita el 3")[0], "2026-10-03")

    def test_un_dia_del_mes_que_no_ha_llegado_es_de_este_mes(self):
        self.assertEqual(self.leer("cita el 20")[0], "2026-09-20")

    def test_con_mes_dicho_se_respeta(self):
        self.assertEqual(self.leer("cita el 3 de octubre")[0], "2026-10-03")

    def test_una_fecha_imposible_no_se_inventa(self):
        self.assertIsNone(self.leer("cita el 31 de febrero"))


class TestLaHoraSeMarcaSiNoEstaAcotada(CasoFechas):
    def test_a_las_cinco_a_secas_sale_sin_acotar(self):
        _, hora, acotada, _ = self.leer("cita el lunes a las 5")
        self.assertEqual(hora, "05:00")
        self.assertFalse(acotada, "nadie dijo si era mañana o tarde")

    def test_a_las_cinco_de_la_tarde_son_las_diecisiete(self):
        _, hora, acotada, _ = self.leer("cita el lunes a las 5 de la tarde")
        self.assertEqual(hora, "17:00")
        self.assertTrue(acotada)

    def test_con_minutos_no_hay_duda(self):
        _, hora, acotada, _ = self.leer("cita el lunes a las 17:30")
        self.assertEqual(hora, "17:30")
        self.assertTrue(acotada)

    def test_las_horas_escritas_con_letra(self):
        self.assertEqual(self.leer("cita el lunes a las cinco")[1], "05:00")
        self.assertEqual(self.leer("cita el lunes a las diez")[1], "10:00")

    def test_y_media_y_y_cuarto(self):
        self.assertEqual(self.leer("cita el lunes a las cinco y media")[1], "05:30")
        self.assertEqual(self.leer("cita el lunes a las diez y cuarto")[1], "10:15")

    def test_una_franja_sin_hora_no_inventa_una_hora(self):
        # «El sábado por la mañana» no son las 09:00. No hay hora.
        _, hora, _, _ = self.leer("hueco el sábado por la mañana")
        self.assertIsNone(hora)

    def test_por_la_manana_no_se_confunde_con_el_dia_manana(self):
        # «mañana» a secas es el día siguiente; «por la mañana» es una franja.
        self.assertEqual(self.leer("hueco el sábado por la mañana")[0], "2026-09-12")
        self.assertEqual(self.leer("hueco mañana")[0], "2026-09-12")


class TestLoQueNoSabeLoDice(CasoFechas):
    def test_sin_dia_devuelve_nada(self):
        # Una hora suelta no es una cita: es media cita, y media cita se
        # pregunta en vez de adivinarse.
        self.assertIsNone(self.leer("quiero cita a las cinco"))

    def test_una_frase_sin_cuando_devuelve_nada(self):
        self.assertIsNone(self.leer("quiero pedir hora"))

    def test_vacio_devuelve_nada(self):
        self.assertIsNone(self.leer("   "))

    def test_sin_tildes_entiende_igual(self):
        # Quien dicta no pone tildes, y Whisper a veces tampoco.
        self.assertEqual(self.leer("cita el miercoles")[0], "2026-09-16")
        self.assertEqual(self.leer("cita pasado manana")[0], "2026-09-13")


class TestElResto(CasoFechas):
    def test_devuelve_la_frase_sin_el_cuando(self):
        _, _, _, resto = self.leer("quiero cita para un tinte el lunes a las 17:30")
        self.assertNotIn("lunes", resto)
        self.assertNotIn("17:30", resto)
        self.assertIn("tinte", resto)


class TestElReloj(unittest.TestCase):
    def test_ahora_es_en_madrid(self):
        self.assertEqual(str(fechas.ahora().tzinfo), "Europe/Madrid")

    def test_hoy_tiene_la_forma_de_siempre(self):
        self.assertRegex(fechas.hoy(), r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
