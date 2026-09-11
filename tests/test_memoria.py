"""Pruebas de la memoria: lo que se recuerda de quien llama, y lo que se borra.

Dos mitades. La primera es que sirva: que a quien viene cada mes a teñirse se
le pueda ofrecer lo de siempre sin que lo repita. La segunda es que no se
pase: que se olvide solo, que se pueda borrar entero, y que un informe no
lleve el nombre ni el teléfono de nadie.
"""

import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

from negocio import agenda as ag  # noqa: E402
from guardado import almacen  # noqa: E402
from mente import memoria  # noqa: E402
from negocio import negocio as negocios  # noqa: E402
from mente import recepcion  # noqa: E402
from telefono import telefonia  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
VIERNES = datetime(2026, 9, 11, 10, 0, tzinfo=MADRID)
JUEVES = "2026-09-17"
UN_NUMERO = "+34600111222"


class CasoMemoria(unittest.TestCase):
    def setUp(self):
        entorno.aislar(self)


class TestLaFicha(CasoMemoria):
    def test_la_primera_llamada_no_sabe_nada(self):
        self.assertIsNone(memoria.ficha(UN_NUMERO))

    def test_se_apunta_la_llamada_y_el_nombre(self):
        memoria.apuntar_llamada(UN_NUMERO, "Marta")
        ficha = memoria.ficha(UN_NUMERO)
        self.assertEqual((ficha.nombre, ficha.llamadas), ("Marta", 1))
        self.assertTrue(ficha.conocido)

    def test_una_llamada_sin_nombre_no_borra_el_de_antes(self):
        memoria.apuntar_llamada(UN_NUMERO, "Marta")
        memoria.apuntar_llamada(UN_NUMERO, None)
        ficha = memoria.ficha(UN_NUMERO)
        self.assertEqual((ficha.nombre, ficha.llamadas), ("Marta", 2))

    def test_un_numero_vacio_no_crea_ficha(self):
        self.assertIsNone(memoria.apuntar_llamada("", "Marta"))
        self.assertEqual(memoria.fichas(), [])

    def test_las_fechas_de_la_primera_y_la_ultima(self):
        ficha = memoria.apuntar_llamada(UN_NUMERO, "Marta")
        self.assertEqual(ficha.primera, ficha.ultima)
        self.assertRegex(ficha.ultima, r"^\d{4}-\d{2}-\d{2}$")


class TestLaCostumbre(CasoMemoria):
    def test_con_una_vez_no_hay_costumbre(self):
        memoria.apuntar_cita(UN_NUMERO, "Tinte", "17:00")
        self.assertIsNone(memoria.ficha(UN_NUMERO).habitual)

    def test_con_dos_veces_ya_es_lo_de_siempre(self):
        memoria.apuntar_cita(UN_NUMERO, "Tinte", "17:00")
        memoria.apuntar_cita(UN_NUMERO, "Tinte", "18:00")
        ficha = memoria.ficha(UN_NUMERO)
        self.assertEqual(ficha.habitual, "Tinte")
        self.assertEqual(ficha.franja, "tarde")
        self.assertEqual(ficha.citas, 2)

    def test_gana_el_que_mas_veces(self):
        for _ in range(3):
            memoria.apuntar_cita(UN_NUMERO, "Mechas", "11:00")
        memoria.apuntar_cita(UN_NUMERO, "Tinte", "17:00")
        memoria.apuntar_cita(UN_NUMERO, "Tinte", "17:00")
        self.assertEqual(memoria.ficha(UN_NUMERO).habitual, "Mechas")
        self.assertEqual(memoria.ficha(UN_NUMERO).franja, "manana")

    def test_la_franja_sale_de_la_hora(self):
        self.assertEqual(memoria.franja_de("09:30"), "manana")
        self.assertEqual(memoria.franja_de("13:59"), "manana")
        self.assertEqual(memoria.franja_de("14:00"), "tarde")
        self.assertIsNone(memoria.franja_de(None))
        self.assertIsNone(memoria.franja_de("no es una hora"))

    def test_las_anulaciones_se_cuentan(self):
        memoria.apuntar_anulacion(UN_NUMERO)
        self.assertEqual(memoria.ficha(UN_NUMERO).anuladas, 1)


class TestOlvidar(CasoMemoria):
    def test_olvidar_borra_de_verdad(self):
        memoria.apuntar_llamada(UN_NUMERO, "Marta")
        self.assertTrue(memoria.olvidar(UN_NUMERO))
        self.assertIsNone(memoria.ficha(UN_NUMERO))
        self.assertEqual(memoria.fichas(), [])

    def test_olvidar_lo_que_no_hay_no_revienta(self):
        self.assertFalse(memoria.olvidar("+34600000000"))

    def test_caducan_las_que_llevan_mucho_sin_llamar(self):
        memoria.apuntar_llamada(UN_NUMERO, "Marta")
        memoria.apuntar_llamada("+34600999888", "Ana")
        # Una de las dos, con la última llamada de hace tres años.
        todas = memoria._todas()
        todas[UN_NUMERO]["ultima"] = "2023-01-01"
        memoria._guardar(todas)

        borradas = memoria.caducar(hoy=date(2026, 9, 11))
        self.assertEqual(borradas, [UN_NUMERO])
        self.assertIsNone(memoria.ficha(UN_NUMERO))
        self.assertIsNotNone(memoria.ficha("+34600999888"))

    def test_una_ficha_sin_fecha_no_se_borra_a_ciegas(self):
        memoria._guardar({UN_NUMERO: {"nombre": "Marta", "llamadas": 1}})
        self.assertEqual(memoria.caducar(hoy=date(2026, 9, 11)), [])
        self.assertIsNotNone(memoria.ficha(UN_NUMERO))


class TestElInformeNoLlevaNombres(CasoMemoria):
    def test_las_cuentas_son_numeros(self):
        memoria.apuntar_llamada(UN_NUMERO, "Marta")
        memoria.apuntar_llamada(UN_NUMERO, "Marta")
        memoria.apuntar_cita(UN_NUMERO, "Tinte", "17:00")
        memoria.apuntar_cita(UN_NUMERO, "Tinte", "17:00")
        memoria.apuntar_llamada("+34600999888", None)

        cuentas = memoria.cuentas()
        self.assertEqual(cuentas, {"fichas": 2, "con_nombre": 1,
                                   "repiten": 1, "con_costumbre": 1})
        self.assertNotIn("Marta", str(cuentas))
        self.assertNotIn(UN_NUMERO, str(cuentas))

    def test_el_diagnostico_no_imprime_ni_un_nombre(self):
        from dueno import diagnostico
        memoria.apuntar_llamada(UN_NUMERO, "Marta")
        informe = "\n".join(diagnostico.negocio_y_datos("peluqueria"))
        self.assertIn("clientes:", informe)
        self.assertNotIn("Marta", informe)
        self.assertNotIn(UN_NUMERO, informe)


class TestLaFichaVieja(CasoMemoria):
    def test_el_clientes_json_de_antes_se_entiende(self):
        # El formato viejo: nombre, llamadas y última. Nadie pierde su nombre
        # porque el fichero haya cambiado de versión.
        almacen.guardar(memoria.ruta(),
                        {UN_NUMERO: {"nombre": "Marta", "llamadas": 3, "ultima": "2026-09-01"}},
                        1)
        ficha = memoria.ficha(UN_NUMERO)
        self.assertEqual((ficha.nombre, ficha.llamadas, ficha.citas), ("Marta", 3, 0))
        self.assertEqual(ficha.primera, "2026-09-01")

    def test_y_se_sigue_completando(self):
        almacen.guardar(memoria.ruta(),
                        {UN_NUMERO: {"nombre": "Marta", "llamadas": 3, "ultima": "2026-09-01"}},
                        1)
        memoria.apuntar_cita(UN_NUMERO, "Tinte", "17:00")
        self.assertEqual(memoria.ficha(UN_NUMERO).servicios, {"Tinte": 1})


class CasoConMemoria(unittest.TestCase):
    """Una llamada de alguien a quien ya se conoce."""

    def setUp(self):
        entorno.aislar(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.negocio = negocios.cargar("peluqueria")
        self.agenda = ag.Agenda("peluqueria", self.negocio.horario,
                                ruta=Path(self._tmp.name) / "agenda.json", ahora=VIERNES)
        self.llamada = recepcion.Conversacion(self.negocio.conocimiento, agenda=self.agenda)

    def con_ficha(self, **datos):
        ficha = memoria.Ficha(telefono=UN_NUMERO, **datos)
        self.llamada.recordar(ficha)
        return ficha

    def texto(self, *frases):
        texto = ""
        for frase in frases:
            texto = self.llamada.atender(frase).texto
        return texto


class TestLoDeSiempre(CasoConMemoria):
    def test_se_le_ofrece_lo_que_pide_siempre(self):
        self.con_ficha(nombre="Marta", servicios={"Tinte": 3})
        dicho = self.texto("hola, quería lo de siempre")
        self.assertIn("tinte como siempre", dicho.lower())
        self.assertEqual(self.llamada.cita.servicio, "Tinte")

    def test_y_la_cita_sigue_su_camino(self):
        self.con_ficha(nombre="Marta", servicios={"Tinte": 3})
        dicho = self.texto("lo de siempre", "el jueves a las cinco de la tarde")
        self.assertIn("Reservada", dicho)
        self.assertEqual(self.agenda.citas()[0]["servicio"], "Tinte")
        self.assertEqual(self.agenda.citas()[0]["nombre"], "Marta")

    def test_sin_costumbre_se_pregunta(self):
        self.con_ficha(nombre="Marta", servicios={"Tinte": 1})
        self.assertIn("qué servicio", self.texto("ponme lo de siempre").lower())

    def test_y_la_cita_queda_abierta_para_lo_que_diga_despues(self):
        self.con_ficha(nombre="Marta", servicios={"Tinte": 1})
        self.texto("lo de siempre")                  # → «¿para qué servicio?»
        self.assertIn("¿A qué hora", self.texto("el jueves"))
        self.texto("un tinte", "a las cinco de la tarde")
        self.assertEqual(self.agenda.citas()[0]["servicio"], "Tinte")

    def test_sin_ficha_tampoco_se_inventa_nada(self):
        self.assertIn("qué servicio", self.texto("lo de siempre").lower())

    def test_un_servicio_que_ya_no_esta_en_la_tabla_no_se_ofrece(self):
        # La tabla manda también sobre lo que recuerda la ficha.
        self.con_ficha(nombre="Marta", servicios={"Extensiones": 5})
        self.assertIn("qué servicio", self.texto("lo de siempre").lower())

    def test_decir_otra_cosa_en_la_misma_frase_manda(self):
        self.con_ficha(nombre="Marta", servicios={"Tinte": 3})
        self.texto("como siempre, pero esta vez quiero cita para unas mechas")
        self.assertEqual(self.llamada.cita.servicio, "Mechas")


class TestLaFranjaDeSiempre(CasoConMemoria):
    def test_se_empieza_por_la_franja_de_costumbre(self):
        self.con_ficha(nombre="Marta", servicios={"Tinte": 3}, franjas={"tarde": 4})
        dicho = self.texto("lo de siempre", "el jueves", "cuando podáis")
        self.assertIn("de la tarde", dicho)
        self.assertNotIn("de la mañana", dicho)

    def test_lo_que_diga_manda_sobre_la_costumbre(self):
        self.con_ficha(nombre="Marta", servicios={"Tinte": 3}, franjas={"tarde": 4})
        dicho = self.texto("quiero cita de tinte el jueves por la mañana, cuando podáis")
        self.assertIn("de la mañana", dicho)

    def test_sin_costumbre_se_ofrece_lo_que_haya(self):
        self.con_ficha(nombre="Marta", servicios={"Tinte": 3})
        dicho = self.texto("lo de siempre", "el jueves", "cuando podáis")
        self.assertIn("de la mañana", dicho)


class TestLaLlamadaAlimentaLaFicha(unittest.TestCase):
    TURNO = "https://maquina.tailnet.ts.net/telefono/turno"

    def setUp(self):
        entorno.aislar(self)
        self.negocio = negocios.cargar("peluqueria")
        self.centralita = telefonia.Centralita(self.negocio)

    def llamar(self, sid, numero=UN_NUMERO):
        return self.centralita.entrada({"CallSid": sid, "From": numero}, self.TURNO)

    def decir(self, sid, frase):
        return self.centralita.turno({"CallSid": sid, "SpeechResult": frase}, self.TURNO)

    def hueco(self, cual=0):
        """Un hueco de verdad de la agenda, no una hora escrita a mano.

        Con fechas a mano —«el viernes a las cinco»— esto dependía de la
        hora a la que se corriera: pasadas las cinco de un viernes esa cita
        ya era pasado y la agenda la rechazaba.
        """
        agenda = ag.Agenda("peluqueria", self.negocio.horario)
        return agenda.proximos_huecos(agenda.ahora().strftime("%Y-%m-%d"), 90,
                                      dias=14, tope=4, por_dia=1)[cual]

    def cuando(self, cual=0):
        """Ese hueco, dicho como lo diría quien llama."""
        from mente import fechas
        hueco = self.hueco(cual)
        ahora = ag.Agenda("peluqueria", self.negocio.horario).ahora()
        return (f"{fechas.en_palabras(hueco.fecha, ahora.date())} "
                f"a {fechas.hora_en_palabras(hueco.hora)}")

    def citarse(self, sid, cuando=None):
        self.llamar(sid)
        self.decir(sid, "quiero cita para un tinte")
        self.decir(sid, cuando or self.cuando(0))
        self.decir(sid, "me llamo Marta")
        self.centralita.fin({"CallSid": sid})

    def test_la_cita_cerrada_se_apunta_en_la_ficha(self):
        # La franja se comprueba contra el hueco que se cogió, no contra una
        # escrita aquí: el primer hueco libre es por la mañana o por la
        # tarde según el día y la hora a la que se corra esto.
        suya = memoria.franja_de(self.hueco(0).hora)
        self.citarse("CA1")
        ficha = memoria.ficha(UN_NUMERO)
        self.assertEqual(ficha.nombre, "Marta")
        self.assertEqual(ficha.citas, 1)
        self.assertEqual(ficha.servicios, {"Tinte": 1})
        self.assertEqual(ficha.franjas, {suya: 1})

    def test_a_la_segunda_ya_hay_costumbre_y_se_le_ofrece(self):
        self.citarse("CA1")
        self.citarse("CA2", self.cuando(1))
        self.assertEqual(memoria.ficha(UN_NUMERO).habitual, "Tinte")

        self.llamar("CA3")
        xml = self.decir("CA3", "hola, lo de siempre")
        self.assertIn("tinte como siempre", xml.lower())

    def test_anular_se_apunta_tambien(self):
        self.citarse("CA1")
        self.llamar("CA2")
        self.decir("CA2", "quiero anular mi cita")
        self.centralita.fin({"CallSid": "CA2"})
        self.assertEqual(memoria.ficha(UN_NUMERO).anuladas, 1)

    def test_un_numero_oculto_no_deja_ficha(self):
        self.llamar("CA1", "")
        self.decir("CA1", "me llamo Marta")
        self.centralita.fin({"CallSid": "CA1"})
        self.assertEqual(memoria.fichas(), [])


if __name__ == "__main__":
    unittest.main()
