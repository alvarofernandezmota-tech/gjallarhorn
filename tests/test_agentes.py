"""Pruebas de los agentes: lo que trabaja cuando no suena el teléfono.

Son funciones puras —se les da el mundo y devuelven texto—, así que aquí se
les da una agenda de mentira y un reloj fijo. Sin eso, la prueba de «las
citas de mañana» solo pasaría si mañana hay citas de verdad, que es lo mismo
que no probarla.

Lo que más se vigila: que **se callen cuando no hay nada**. Un agente que
manda un aviso cada mañana diciendo que no hay novedades es un agente que se
deja de leer a la semana, y con él se dejan de leer los que sí traían algo.
"""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

import agenda as ag  # noqa: E402
import agentes  # noqa: E402
import avisos  # noqa: E402
import memoria  # noqa: E402
import negocio as negocios  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
VIERNES = datetime(2026, 9, 11, 10, 0, tzinfo=MADRID)
SABADO, JUEVES = "2026-09-12", "2026-09-17"


class CasoAgentes(unittest.TestCase):
    def setUp(self):
        entorno.aislar(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.negocio = negocios.cargar("peluqueria")
        self.agenda = ag.Agenda("peluqueria", self.negocio.horario,
                                ruta=Path(self._tmp.name) / "agenda.json", ahora=VIERNES)

    def mundo(self, fichas=None, con_agenda=True):
        return agentes.Mundo(negocio=self.negocio,
                             agenda=self.agenda if con_agenda else None,
                             ahora=VIERNES, fichas=fichas or [])

    def ficha(self, **datos):
        datos.setdefault("telefono", "+34600111222")
        return memoria.Ficha(**datos)


class TestRecordatorios(CasoAgentes):
    def test_sin_citas_manana_no_dice_nada(self):
        self.assertIsNone(agentes.recordatorios(self.mundo()))

    def test_las_citas_de_manana_con_su_mensaje(self):
        self.agenda.reservar(SABADO, "10:00", 30, "Corte de caballero", "Luis")
        self.agenda.reservar(SABADO, "11:00", 90, "Tinte", "Marta")
        resultado = agentes.recordatorios(self.mundo())
        self.assertIn("2 cita(s) mañana", resultado.texto())
        self.assertIn("10:00 Luis", resultado.texto())
        self.assertIn("11:00 Marta", resultado.texto())
        self.assertIn("Le recordamos su cita de tinte mañana a las once", resultado.texto())

    def test_las_de_hoy_o_pasado_no_son_las_de_manana(self):
        self.agenda.reservar(JUEVES, "10:00", 30, "Corte de caballero", "Luis")
        self.assertIsNone(agentes.recordatorios(self.mundo()))

    def test_sin_agenda_no_hay_recordatorios(self):
        self.assertIsNone(agentes.recordatorios(self.mundo(con_agenda=False)))


class TestResumen(CasoAgentes):
    def test_cuenta_las_citas_y_lo_previsto(self):
        self.agenda.reservar("2026-09-11", "11:00", 90, "Tinte", "Marta")
        self.agenda.reservar("2026-09-11", "13:00", 30, "Corte de caballero", "Luis")
        texto = agentes.resumen(self.mundo()).texto()
        self.assertIn("2 cita(s) hoy", texto)
        self.assertIn("59 €", texto)          # 45 + 14, de la tabla
        self.assertIn("hueco(s) todavía libres", texto)

    def test_un_servicio_sin_precio_se_dice_aparte(self):
        self.agenda.reservar("2026-09-11", "11:00", 30, "Algo raro", "Marta")
        self.agenda.reservar("2026-09-11", "12:00", 30, "Corte de caballero", "Luis")
        texto = agentes.resumen(self.mundo()).texto()
        self.assertIn("14 €", texto)
        self.assertIn("1 sin precio", texto)

    def test_los_avisos_sin_ver_salen_en_el_resumen(self):
        avisos.registrar("cita", "algo que nadie ha mirado")
        self.assertIn("1 aviso(s) sin ver", agentes.resumen(self.mundo()).texto())


class TestHuecos(CasoAgentes):
    def test_una_semana_sin_ninguna_cita_no_es_una_semana_floja(self):
        # Es un negocio que empieza, o agosto. Avisar de eso cada mañana es ruido.
        self.assertIsNone(agentes.huecos(self.mundo()))

    def test_con_citas_dice_que_dias_estan_flojos(self):
        self.agenda.reservar("2026-09-11", "11:00", 90, "Tinte", "Marta")
        resultado = agentes.huecos(self.mundo())
        self.assertIn("Días flojos", resultado.texto())
        self.assertIn("huecos libres", resultado.texto())

    def test_sugiere_a_quien_ofrecerselo(self):
        self.agenda.reservar("2026-09-11", "11:00", 90, "Tinte", "Marta")
        fichas = [self.ficha(nombre="Marta", citas=3), self.ficha(nombre="Nuevo", citas=1)]
        texto = agentes.huecos(self.mundo(fichas)).texto()
        self.assertIn("Marta", texto)
        self.assertNotIn("Nuevo", texto, "quien ha venido una vez no es un habitual")


class TestSeguimiento(CasoAgentes):
    def test_quien_lleva_medio_ano_sin_venir(self):
        fichas = [self.ficha(nombre="Marta", citas=4, ultima="2025-01-10"),
                  self.ficha(nombre="Luis", citas=3, ultima="2026-09-01")]
        texto = agentes.seguimiento(self.mundo(fichas)).texto()
        self.assertIn("Marta", texto)
        self.assertNotIn("Luis", texto)

    def test_quien_vino_una_vez_no_cuenta_como_perdido(self):
        fichas = [self.ficha(nombre="De paso", citas=1, ultima="2024-01-01")]
        self.assertIsNone(agentes.seguimiento(self.mundo(fichas)))

    def test_sin_nadie_perdido_no_dice_nada(self):
        self.assertIsNone(agentes.seguimiento(self.mundo()))


class TestRevision(CasoAgentes):
    def test_un_negocio_bien_puesto_no_da_nada_que_decir(self):
        self.assertIsNone(agentes.revision(self.mundo()))

    def test_avisa_de_dos_citas_que_se_pisan(self):
        # A mano, saltándose la agenda: por eso es un fallo que hay que ver.
        self.agenda._guardar([
            {"id": 1, "fecha": JUEVES, "hora": "10:00", "duracion": 90,
             "servicio": "Tinte", "nombre": "Marta", "creada": "2026-09-11 10:00"},
            {"id": 2, "fecha": JUEVES, "hora": "11:00", "duracion": 30,
             "servicio": "Corte de caballero", "nombre": "Luis", "creada": "2026-09-11 10:00"},
        ])
        resultado = agentes.revision(self.mundo())
        self.assertIn("se pisan", resultado.texto())
        self.assertEqual(resultado.tipo, "fallo")

    def test_avisa_de_las_tarifas_sin_duracion(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        (base / "tarifas.md").write_text("| Servicio | Precio |\n|---|---|\n| Corte | 14 € |\n",
                                         encoding="utf-8")
        (base / "faq.md").write_text("**¿Horario?**\nDe 10 a 20.\n", encoding="utf-8")
        mundo = self.mundo()
        mundo.negocio = negocios.Negocio(
            nombre="Prueba", ruta=base, saludo="Hola. Le atiende un asistente automático.",
            despedida="Adiós", horario=self.negocio.horario)
        self.assertIn("sin duración", agentes.revision(mundo).texto())

    def test_borra_las_fichas_caducadas_y_lo_dice(self):
        memoria.apuntar_llamada("+34600111222", "Antigua")
        todas = memoria._todas()
        todas["+34600111222"]["ultima"] = "2020-01-01"
        memoria._guardar(todas)
        texto = agentes.revision(self.mundo()).texto()
        self.assertIn("ficha(s) de clientes borradas", texto)
        self.assertEqual(memoria.fichas(), [])


class TestCorrerlos(CasoAgentes):
    def test_en_seco_no_escribe_nada(self):
        self.agenda.reservar(SABADO, "10:00", 30, "Corte de caballero", "Luis")
        resultados = agentes.correr(self.negocio, ahora=VIERNES, registrar=False)
        self.assertTrue(resultados)
        self.assertEqual(avisos.listar(), [])

    def test_registrando_deja_un_aviso_por_agente(self):
        self.agenda.reservar(SABADO, "10:00", 30, "Corte de caballero", "Luis")
        resultados = agentes.correr(self.negocio, ahora=VIERNES)
        self.assertEqual(len(avisos.listar()), len(resultados))

    def test_se_puede_correr_uno_solo(self):
        resultados = agentes.correr(self.negocio, ["resumen"], ahora=VIERNES, registrar=False)
        self.assertEqual([r.agente for r in resultados], ["resumen"])

    def test_un_agente_roto_no_tumba_a_los_demas(self):
        def roto(mundo):
            raise ValueError("me he roto")

        agentes.TODOS["roto"] = roto
        self.addCleanup(lambda: agentes.TODOS.pop("roto", None))
        resultados = agentes.correr(self.negocio, ["roto", "resumen"],
                                    ahora=VIERNES, registrar=False)
        self.assertEqual(len(resultados), 2)
        self.assertIn("ha fallado", resultados[0].texto())
        self.assertEqual(resultados[0].tipo, "fallo")

    def test_un_negocio_tranquilo_no_manda_nada(self):
        # Sin citas, sin fichas y con todo bien puesto: silencio.
        resultados = agentes.correr(self.negocio, ["recordatorios", "seguimiento", "revision"],
                                    ahora=VIERNES)
        self.assertEqual(resultados, [])
        self.assertEqual(avisos.listar(), [])


if __name__ == "__main__":
    unittest.main()
