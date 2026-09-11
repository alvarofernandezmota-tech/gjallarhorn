"""Pruebas de la conversación «profesional»: lo que faltaba visto desde fuera.

Salieron de una llamada simulada entera (`python3 telefonia.py --simular`),
no de leer el código. Cada clase es un fallo que oía quien llamaba:

- «hola, buenas» → «tomo nota y le devolvemos la llamada».
- «vale, pues nada, gracias» → el precio de algo, por el «vale».
- «¿aceptáis tarjeta?» → recado, con la respuesta escrita en la FAQ.
- «el jueves por la tarde» y luego «a las cinco» → «¿las cinco de la tarde?».
- «a nombre de Lucía» después de reservar → nada, la cita seguía a nombre
  de quien llamaba.
- «gracias, ¿y cuánto vale un tinte?» → contestaba el precio y COLGABA.
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
import fechas  # noqa: E402
import negocio as negocios  # noqa: E402
import recepcion  # noqa: E402
import telefonia  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
VIERNES = datetime(2026, 9, 11, 10, 0, tzinfo=MADRID)
JUEVES = "2026-09-17"


class CasoProfesional(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.negocio = negocios.cargar("peluqueria")
        self.agenda = ag.Agenda("peluqueria", self.negocio.horario,
                                ruta=Path(self._tmp.name) / "agenda.json", ahora=VIERNES)
        self.llamada = recepcion.Conversacion(self.negocio.conocimiento, agenda=self.agenda)

    def decir(self, *frases):
        respuesta = None
        for frase in frases:
            respuesta = self.llamada.atender(frase)
        return respuesta

    def texto(self, *frases):
        return self.decir(*frases).texto


class TestSaludoYDespedida(CasoProfesional):
    def test_un_saludo_a_secas_invita_a_hablar(self):
        respuesta = self.decir("hola, buenas")
        self.assertIn("Dígame", respuesta.texto)
        self.assertIsNone(respuesta.aviso, "un saludo no es un recado")

    def test_un_saludo_no_cuenta_como_no_entender(self):
        self.decir("hola", "buenas tardes", "oiga")
        self.assertFalse(self.decir("hola").cuelga)

    def test_un_saludo_con_pregunta_es_la_pregunta(self):
        self.assertIn("45", self.texto("hola, buenas, ¿cuánto vale un tinte?", "el tinte"))

    def test_vale_pues_nada_gracias_es_la_despedida_no_un_precio(self):
        respuesta = self.decir("vale, pues nada, gracias")
        self.assertIn("Hasta luego", respuesta.texto)
        self.assertTrue(respuesta.cuelga)

    def test_a_la_tercera_sin_entender_se_toma_el_recado_y_se_cuelga(self):
        self.decir("xyzzy", "plugh")
        respuesta = self.decir("frobnicar")
        self.assertIn("no acabo de entenderle", respuesta.texto)
        self.assertTrue(respuesta.cuelga)


class TestPrecioSinNombrarElServicio(CasoProfesional):
    def test_sin_haber_hablado_de_nada_se_pregunta_el_que(self):
        respuesta = self.decir("¿cuánto me va a costar?")
        self.assertIn("¿De qué servicio?", respuesta.texto)
        self.assertIsNone(respuesta.aviso, "no es un fallo de tarifas, es una pregunta")

    def test_y_al_decir_el_que_se_da_el_precio(self):
        self.assertIn("45", self.texto("¿cuánto me va a costar?", "un tinte"))

    def test_del_que_se_venia_hablando(self):
        self.assertIn("65", self.texto("¿cuánto valen las mechas?", "¿y cuánto me va a costar entonces?"))

    def test_con_varias_opciones_abiertas_se_vuelve_a_preguntar_cual(self):
        primera = self.texto("¿cuánto vale el tinte?")
        self.assertIn("¿Cuál le interesa?", primera)
        self.assertIn("¿Cuál le interesa?", self.texto("¿y cuánto tarda?"))
        self.assertIn("una hora y media", self.texto("el tinte"))

    def test_otra_cosa_que_no_esta_sigue_sin_estar(self):
        # La regla de siempre: nombrar otra cosa NO devuelve el precio anterior.
        dicho = self.texto("¿cuánto vale el tinte?", "¿y un masaje cuánto cuesta?")
        self.assertNotIn("45", dicho)
        self.assertIn("No tengo ese servicio", dicho)

    def test_cuanto_tarda_da_el_servicio_con_su_duracion(self):
        self.assertIn("dos horas", self.texto("¿cuánto valen las mechas?", "¿y cuánto tarda?"))

    def test_cuanto_tarda_nombrando_el_servicio(self):
        self.assertIn("dos horas", self.texto("¿cuánto tardan las mechas?"))


class TestLaFaqContesta(CasoProfesional):
    def test_tarjeta(self):
        self.assertIn("Bizum y efectivo", self.texto("¿aceptáis tarjeta?"))

    def test_donde(self):
        self.assertIn("En el centro", self.texto("¿dónde estáis?"))

    def test_la_hipotetica_no_anula_nada(self):
        self.agenda.reservar(JUEVES, "17:00", 90, "Tinte", "Marta")
        self.llamada.nombre = "Marta"
        dicho = self.texto("¿y si no puedo ir?")
        self.assertIn("cuatro horas", dicho)
        self.assertEqual(len(self.agenda.citas()), 1, "una pregunta no anula la cita")

    def test_no_puedo_ir_sin_condicional_si_anula(self):
        self.agenda.reservar(JUEVES, "17:00", 90, "Tinte", "Marta")
        self.llamada.nombre = "Marta"
        self.assertIn("anulo", self.texto("no voy a poder ir").lower())
        self.assertEqual(self.agenda.citas(), [])

    def test_en_mitad_de_una_cita_se_contesta_y_se_retoma(self):
        dicho = self.texto("quiero cita", "el jueves", "¿aceptáis tarjeta?")
        self.assertIn("Bizum y efectivo", dicho)
        self.assertIn("¿A qué hora", dicho)

    def test_el_precio_en_mitad_de_una_cita_tambien_retoma(self):
        dicho = self.texto("quiero cita", "el jueves", "¿cuánto valen las mechas?")
        self.assertIn("65", dicho)
        self.assertIn("¿A qué hora", dicho)

    def test_lo_que_no_esta_en_la_faq_sigue_siendo_recado(self):
        self.assertIn("Tomo nota", self.texto("¿vendéis pelucas?"))

    def test_cualquier_md_del_negocio_contesta(self):
        # servicios.md no es la FAQ: es otro fichero que dejó el dueño.
        self.assertIn("parking", self.texto("¿tenéis aparcamiento?"))


class TestLaFranjaSeRecuerda(CasoProfesional):
    def test_dicha_con_el_dia_no_se_vuelve_a_preguntar(self):
        dicho = self.texto("quiero cita", "el jueves por la tarde", "a las cinco")
        self.assertIn("¿A nombre de quién", dicho, "las cinco de la tarde ya estaban dichas")
        self.assertEqual((self.llamada.cita.hora, self.llamada.cita.acotada), ("17:00", True))

    def test_dicha_al_preguntar_la_hora(self):
        dicho = self.texto("quiero cita", "el jueves", "por la mañana")
        self.assertIn("por la mañana", dicho)
        self.assertIn("¿A qué hora", dicho)
        self.decir("a las once")
        self.assertEqual((self.llamada.cita.hora, self.llamada.cita.acotada), ("11:00", True))

    def test_la_hora_con_su_propia_franja_manda(self):
        self.decir("quiero cita", "el jueves por la mañana", "a las cinco de la tarde")
        self.assertEqual(self.llamada.cita.hora, "17:00")


class TestElNombreDespuesDeReservar(CasoProfesional):
    def reservar(self):
        self.decir("quiero cita de tinte", "el jueves", "a las cinco de la tarde", "Marta")
        return self.agenda.citas()[0]

    def test_a_nombre_de_corrige_la_reserva(self):
        self.reservar()
        dicho = self.texto("a nombre de Lucía")
        self.assertIn("Lucía", dicho)
        self.assertEqual(self.agenda.citas()[0]["nombre"], "Lucía")
        self.assertEqual(len(self.agenda.citas()), 1, "corrige, no abre otra")

    def test_quien_llama_sigue_siendo_quien_llama(self):
        self.reservar()
        self.decir("a nombre de Lucía")
        self.assertEqual(self.llamada.nombre, "Marta")
        self.assertIsNone(self.llamada.presentado)

    def test_presentarse_si_cambia_quien_llama(self):
        self.decir("soy Ana y quería cita")
        self.assertEqual((self.llamada.nombre, self.llamada.presentado), ("Ana", "Ana"))

    def test_la_cita_de_tinte_no_es_de_nadie_que_se_llame_tinte(self):
        self.decir("quiero la cita de tinte")
        self.assertIsNone(self.llamada.nombre)

    def test_anular_la_cita_de_otra_persona(self):
        self.agenda.reservar(JUEVES, "17:00", 90, "Tinte", "Lucía")
        self.llamada.nombre = "Marta"
        self.assertIn("anulo", self.texto("quiero anular la cita de Lucía").lower())
        self.assertEqual(self.agenda.citas(), [])


class TestAlgoMas(CasoProfesional):
    def reservar(self):
        return self.texto("quiero cita de tinte", "el jueves", "a las cinco de la tarde", "Marta")

    def test_tras_reservar_se_pregunta_si_algo_mas(self):
        self.assertIn("¿Le puedo ayudar en algo más?", self.reservar())

    def test_no_gracias_es_la_despedida(self):
        self.reservar()
        respuesta = self.decir("no, gracias")
        self.assertTrue(respuesta.cuelga)
        self.assertIn("Hasta luego", respuesta.texto)

    def test_un_no_a_secas_tambien(self):
        self.reservar()
        self.assertTrue(self.decir("no").cuelga)

    def test_si_invita_a_seguir(self):
        self.reservar()
        self.assertIn("Dígame", self.texto("sí"))

    def test_otra_pregunta_se_atiende_normal(self):
        self.reservar()
        self.assertIn("65", self.texto("¿cuánto valen las mechas?"))

    def test_tras_anular_tambien(self):
        self.agenda.reservar(JUEVES, "17:00", 90, "Tinte", "Marta")
        self.llamada.nombre = "Marta"
        self.assertIn("algo más", self.texto("quiero anular mi cita"))


class TestFechasNuevas(unittest.TestCase):
    def test_franja_en(self):
        self.assertEqual(fechas.franja_en("el jueves por la tarde"), "tarde")
        self.assertEqual(fechas.franja_en("esta mañana"), "manana")
        self.assertEqual(fechas.franja_en("a mediodía"), "mediodia")
        self.assertIsNone(fechas.franja_en("mañana"), "«mañana» a secas es el día")
        self.assertIsNone(fechas.franja_en("el jueves"))

    def test_acotar(self):
        self.assertEqual(fechas.acotar("05:00", "tarde"), "17:00")
        self.assertEqual(fechas.acotar("11:00", "manana"), "11:00")
        self.assertEqual(fechas.acotar("02:00", "mediodia"), "14:00")
        self.assertEqual(fechas.acotar("17:00", "tarde"), "17:00")

    def test_las_dos_del_mediodia_son_las_catorce(self):
        fecha, hora, acotada, _ = fechas.interpretar("el jueves a las dos del mediodía", VIERNES)
        self.assertEqual((hora, acotada), ("14:00", True))


class TestAgendaRenombrar(unittest.TestCase):
    def test_renombrar(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        negocio = negocios.cargar("peluqueria")
        agenda = ag.Agenda("peluqueria", negocio.horario, ruta=Path(tmp.name) / "a.json", ahora=VIERNES)
        cita = agenda.reservar(JUEVES, "17:00", 90, "Tinte", "Marta")
        self.assertEqual(agenda.renombrar(cita["id"], "Lucía")["nombre"], "Lucía")
        self.assertEqual(agenda.citas()[0]["nombre"], "Lucía")
        self.assertIsNone(agenda.renombrar(99, "Nadie"))


class TestTelefoniaProfesional(unittest.TestCase):
    TURNO = "https://maquina.tailnet.ts.net/telefono/turno"

    def setUp(self):
        entorno.aislar(self)
        self.negocio = negocios.cargar("peluqueria")
        self.centralita = telefonia.Centralita(self.negocio)

    def llamar(self, sid, numero="+34600000001"):
        return self.centralita.entrada({"CallSid": sid, "From": numero}, self.TURNO)

    def decir(self, sid, frase):
        return self.centralita.turno({"CallSid": sid, "SpeechResult": frase}, self.TURNO)

    def test_no_se_saluda_dos_veces_a_quien_se_conoce(self):
        self.assertEqual(telefonia.saludo_a("Marta", "Hola, ha llamado a la peluquería."),
                         "Hola, Marta. Ha llamado a la peluquería.")
        self.assertEqual(telefonia.saludo_a("Marta", "Buenas, peluquería Sol."),
                         "Hola, Marta. Peluquería Sol.")
        self.assertEqual(telefonia.saludo_a("Marta", "Peluquería Sol, dígame."),
                         "Hola, Marta. Peluquería Sol, dígame.")

    def test_gracias_con_pregunta_no_cuelga(self):
        self.llamar("CA1")
        xml = self.decir("CA1", "gracias, ¿y cuánto vale un tinte?")
        self.assertNotIn("<Hangup/>", xml)
        self.assertIn("<Gather", xml)

    def test_colgar_nosotros_apunta_la_cita_a_medias_sin_esperar_al_proveedor(self):
        self.llamar("CA1")
        self.decir("CA1", "quiero cita de tinte el jueves")
        xml = self.decir("CA1", "gracias, adiós")
        self.assertIn("<Hangup/>", xml)
        self.assertNotIn("CA1", self.centralita._llamadas)
        # El /fin del proveedor llega después y sigue sabiendo en qué quedó.
        quedo = self.centralita.fin({"CallSid": "CA1"})
        self.assertIn("a medias", quedo)
        self.assertIsNone(self.centralita.fin({"CallSid": "CA1"}))

    def test_a_nombre_de_otra_no_cambia_quien_llama(self):
        self.llamar("CA1", "+34600000007")
        self.decir("CA1", "me llamo Marta")
        self.centralita.fin({"CallSid": "CA1"})
        self.llamar("CA2", "+34600000007")
        for frase in ("quiero cita de tinte", "el jueves", "a las cinco de la tarde",
                      "a nombre de Lucía"):
            self.decir("CA2", frase)
        self.centralita.fin({"CallSid": "CA2"})
        self.assertEqual(telefonia.cliente("+34600000007")["nombre"], "Marta")
        self.assertEqual(telefonia.cliente("+34600000007")["llamadas"], 2)

    def test_presentarse_si_corrige_el_nombre_recordado(self):
        self.llamar("CA1", "+34600000008")
        self.decir("CA1", "me llamo Marta")
        self.centralita.fin({"CallSid": "CA1"})
        self.llamar("CA2", "+34600000008")
        self.decir("CA2", "soy Ana")
        self.centralita.fin({"CallSid": "CA2"})
        self.assertEqual(telefonia.cliente("+34600000008")["nombre"], "Ana")

    def test_recordar_sin_nombre_solo_cuenta_si_ya_se_conocia(self):
        telefonia.recordar_cliente("+34600000009", None)
        self.assertIsNone(telefonia.cliente("+34600000009"))
        telefonia.recordar_cliente("+34600000009", "Marta")
        telefonia.recordar_cliente("+34600000009", None)
        self.assertEqual(telefonia.cliente("+34600000009")["llamadas"], 2)


if __name__ == "__main__":
    unittest.main()
