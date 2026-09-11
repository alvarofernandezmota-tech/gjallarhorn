"""Pruebas del panel del dueño: lo que enseña, lo que deja hacer y dónde vive.

Lo tercero es lo que más importa. El panel enseña nombres y teléfonos de
clientes —es la libreta del dueño, y sin nombres no sirve—, así que la prueba
que no se puede caer es que **el puerto público no lo conoce**: ni la página,
ni los datos, ni el botón de anular.
"""

import io
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

import agenda as _agenda  # noqa: E402
import avisos  # noqa: E402
import memoria  # noqa: E402
import negocio as negocios  # noqa: E402
import panel  # noqa: E402
import servidor  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
VIERNES = datetime(2026, 9, 11, 10, 0, tzinfo=MADRID)   # la peluquería abre
LUNES = datetime(2026, 9, 14, 10, 0, tzinfo=MADRID)     # cerrado


class CasoPanel(unittest.TestCase):
    def setUp(self):
        entorno.aislar(self)
        self.negocio = negocios.cargar("peluqueria")
        self.agenda = _agenda.Agenda("peluqueria", self.negocio.horario, ahora=VIERNES)

    def reservar(self, hora="17:00", servicio="Tinte", nombre="Marta", fecha="2026-09-11"):
        return self.agenda.reservar(fecha, hora, 90, servicio, nombre)

    def vista(self, ahora=VIERNES):
        return panel.vista(self.negocio, ahora=ahora)


class TestElDia(CasoPanel):
    def test_las_citas_de_hoy_salen_con_su_hora_dicha(self):
        self.reservar()
        hoy = self.vista()["dias"][0]
        self.assertEqual(hoy["fecha"], "2026-09-11")
        self.assertEqual(hoy["dicho"], "hoy")
        self.assertEqual(len(hoy["citas"]), 1)
        self.assertEqual(hoy["citas"][0]["hora"], "17:00")
        self.assertIn("cinco de la tarde", hoy["citas"][0]["dicha"])
        self.assertEqual(hoy["citas"][0]["nombre"], "Marta")

    def test_el_precio_sale_de_la_tabla_y_se_suma(self):
        self.reservar(servicio="Tinte")
        self.reservar(hora="11:00", servicio="Mechas", nombre="Ana")
        hoy = self.vista()["dias"][0]
        self.assertEqual(hoy["previsto"], 110.0)      # 45 + 65, de tarifas.md
        self.assertEqual(hoy["sin_precio"], 0)
        self.assertEqual([c["precio"] for c in hoy["citas"]], ["65 €", "45 €"])

    def test_una_cita_sin_servicio_no_suma_un_cero_disimulado(self):
        self.reservar(servicio=None)
        hoy = self.vista()["dias"][0]
        self.assertEqual(hoy["previsto"], 0.0)
        self.assertEqual(hoy["sin_precio"], 1)

    def test_las_citas_van_en_orden_de_hora(self):
        self.reservar(hora="18:30", nombre="Tarde")
        self.reservar(hora="11:00", nombre="Mañana")
        horas = [c["hora"] for c in self.vista()["dias"][0]["citas"]]
        self.assertEqual(horas, sorted(horas))

    def test_los_huecos_libres_de_hoy_cuentan_desde_el_reloj(self):
        hoy = self.vista()["dias"][0]
        self.assertTrue(hoy["huecos"], "a las diez de la mañana queda día por delante")
        # Ninguno anterior a la hora que es: un hueco que ya pasó no es un hueco.
        self.assertNotIn("las nueve de la mañana", hoy["huecos"])

    def test_manana_tambien_se_ve(self):
        self.reservar(fecha="2026-09-12", hora="10:00", nombre="Luis")
        dias = self.vista()["dias"]
        self.assertEqual(len(dias), 2)
        self.assertEqual(dias[1]["dicho"], "mañana")
        self.assertEqual(dias[1]["citas"][0]["nombre"], "Luis")

    def test_un_dia_cerrado_lo_dice_y_no_ofrece_huecos(self):
        lunes = panel.vista(self.negocio, ahora=LUNES)["dias"][0]
        self.assertTrue(lunes["cerrado"])
        self.assertEqual(lunes["huecos"], [])

    def test_sin_horario_no_hay_agenda_pero_el_panel_sigue_en_pie(self):
        sin_horario = negocios.cargar("peluqueria")
        object.__setattr__(sin_horario, "horario", None)
        datos = panel.vista(sin_horario, ahora=VIERNES)
        self.assertEqual(datos["dias"][0]["citas"], [])
        self.assertEqual(datos["cuentas"]["citas_hoy"], 0)


class TestElTelefonoDelCliente(CasoPanel):
    def test_se_cruza_por_nombre_con_la_memoria(self):
        memoria.apuntar_llamada("+34600111222", "Marta")
        self.reservar(nombre="Marta")
        cita = self.vista()["dias"][0]["citas"][0]
        self.assertEqual(cita["telefono"], "+34600111222")

    def test_sin_ficha_no_se_inventa_un_telefono(self):
        self.reservar(nombre="Quien Sea")
        self.assertEqual(self.vista()["dias"][0]["citas"][0]["telefono"], "")

    def test_las_tildes_no_esconden_a_nadie(self):
        memoria.apuntar_llamada("+34600333444", "Álvaro")
        self.reservar(nombre="Alvaro")
        self.assertEqual(self.vista()["dias"][0]["citas"][0]["telefono"], "+34600333444")


class TestLosAvisos(CasoPanel):
    def test_los_ultimos_primero_y_los_nuevos_marcados(self):
        avisos.registrar("llamada", "la primera")
        avisos.registrar("fallo", "la última")
        datos = self.vista()
        self.assertEqual(datos["avisos"][0]["texto"], "la última")
        self.assertFalse(datos["avisos"][0]["visto"])
        self.assertEqual(datos["cuentas"]["sin_ver"], 2)

    def test_darlos_por_leidos(self):
        avisos.registrar("llamada", "una cosa")
        self.assertEqual(panel.marcar_vistos(), 1)
        self.assertEqual(self.vista()["cuentas"]["sin_ver"], 0)

    def test_no_se_enseñan_mil(self):
        for numero in range(panel.TOPE_AVISOS + 5):
            avisos.registrar("llamada", f"aviso {numero}")
        self.assertEqual(len(self.vista()["avisos"]), panel.TOPE_AVISOS)


class TestAnularDesdeElPanel(CasoPanel):
    def test_quita_la_cita_y_libera_el_hueco(self):
        cita = self.reservar()
        quitada = panel.anular(self.negocio, cita["id"], ahora=VIERNES)
        self.assertEqual(quitada["nombre"], "Marta")
        self.assertEqual(self.agenda.citas(), [])

    def test_deja_rastro_y_se_ve_que_fue_del_panel(self):
        cita = self.reservar()
        panel.anular(self.negocio, cita["id"], ahora=VIERNES)
        ultimo = avisos.listar()[-1]
        self.assertIn("ANULADA desde el panel", ultimo["texto"])
        self.assertIn("Marta", ultimo["texto"])

    def test_una_cita_que_ya_no_esta_no_revienta(self):
        self.assertIsNone(panel.anular(self.negocio, 99, ahora=VIERNES))

    def test_se_le_apunta_la_anulacion_a_quien_la_tenia(self):
        memoria.apuntar_llamada("+34600111222", "Marta")
        cita = self.reservar(nombre="Marta")
        panel.anular(self.negocio, cita["id"], ahora=VIERNES)
        self.assertEqual(memoria.ficha("+34600111222").anuladas, 1)


class CasoHandler(unittest.TestCase):
    """El mismo montaje que en test_telefonia: un handler a mano, sin sockets."""

    def setUp(self):
        entorno.aislar(self)
        servidor.Comun.negocio = negocios.cargar("peluqueria")
        servidor.Comun.centralita = None
        servidor.Comun.config_telefono = None
        servidor.Comun.transcriptor = None
        servidor.Comun.locutor = None
        servidor.Comun.conversacion = None

    def peticion(self, clase, metodo, ruta, cuerpo=b"", funnel=False):
        h = clase.__new__(clase)
        h.headers = {"Content-Length": str(len(cuerpo)), "Host": "maquina.tailnet.ts.net",
                     "X-Forwarded-Proto": "https"}
        if funnel:
            h.headers["Tailscale-Funnel-Request"] = "?1"
        h.path = ruta
        h.rfile = io.BytesIO(cuerpo)
        h.client_address = ("127.0.0.1", 0)
        h.request_version = "HTTP/1.1"
        h.close_connection = False
        salida = {}
        h._responder = lambda codigo, cuerpo, tipo: salida.update(
            codigo=codigo, cuerpo=cuerpo, tipo=tipo)
        getattr(h, metodo)()
        return salida


class TestElPanelPorHttp(CasoHandler):
    def test_la_pagina_se_sirve_con_el_nombre_del_negocio(self):
        salida = self.peticion(servidor.Recepcion, "do_GET", "/panel")
        self.assertEqual(salida["codigo"], 200)
        self.assertIn(b"Peluquer", salida["cuerpo"])
        self.assertNotIn(b"{{NEGOCIO}}", salida["cuerpo"])

    def test_los_datos_llegan_en_json(self):
        salida = self.peticion(servidor.Recepcion, "do_GET", "/panel/datos")
        datos = json.loads(salida["cuerpo"])
        self.assertEqual(salida["codigo"], 200)
        self.assertIn("dias", datos)
        self.assertIn("cuentas", datos)

    def test_anular_por_http(self):
        # En el primer hueco que haya de verdad, no en una hora inventada: si
        # se elige a mano, la prueba se salta sola el día que cambie el horario.
        agenda = _agenda.Agenda("peluqueria", servidor.Comun.negocio.horario)
        hoy = agenda.ahora().date().isoformat()
        huecos = agenda.proximos_huecos(hoy, 30, tope=1)
        self.assertTrue(huecos, "el negocio de ejemplo no tiene ningún hueco")
        cita = agenda.reservar(huecos[0].fecha, huecos[0].hora, 30, "Tinte", "Marta")
        cuerpo = json.dumps({"id": cita["id"]}).encode()
        salida = self.peticion(servidor.Recepcion, "do_POST", "/panel/anular", cuerpo)
        self.assertEqual(json.loads(salida["cuerpo"])["anulada"]["nombre"], "Marta")

    def test_un_id_que_no_es_un_numero_no_busca_nada(self):
        for cuerpo in (b'{"id": "3 or 1=1"}', b'{"id": null}', b"no soy json", b"",
                       b'{"id": true}', b'["3"]'):
            salida = self.peticion(servidor.Recepcion, "do_POST", "/panel/anular", cuerpo)
            self.assertEqual(salida["codigo"], 200, cuerpo)
            self.assertIsNone(json.loads(salida["cuerpo"])["anulada"], cuerpo)

    def test_dar_por_leidos_por_http(self):
        avisos.registrar("llamada", "algo")
        salida = self.peticion(servidor.Recepcion, "do_POST", "/panel/vistos", b"{}")
        self.assertEqual(json.loads(salida["cuerpo"])["vistos"], 1)


class TestElPanelNoSaleDeCasa(CasoHandler):
    """La prueba que no se puede caer: aquí hay nombres y teléfonos."""

    RUTAS_GET = ("/panel", "/panel/datos")
    RUTAS_POST = ("/panel/anular", "/panel/vistos")

    def test_el_puerto_publico_no_conoce_el_panel(self):
        servidor.Comun.config_telefono = {"token": "secreto", "voz": "Polly.Lucia"}
        for ruta in self.RUTAS_GET:
            self.assertEqual(self.peticion(servidor.Telefono, "do_GET", ruta)["codigo"], 404, ruta)
        for ruta in self.RUTAS_POST:
            self.assertEqual(
                self.peticion(servidor.Telefono, "do_POST", ruta, b"{}")["codigo"], 404, ruta)

    def test_con_la_marca_de_funnel_tampoco_en_el_puerto_privado(self):
        for ruta in self.RUTAS_GET:
            salida = self.peticion(servidor.Recepcion, "do_GET", ruta, funnel=True)
            self.assertEqual(salida["codigo"], 404, ruta)
        for ruta in self.RUTAS_POST:
            salida = self.peticion(servidor.Recepcion, "do_POST", ruta, b"{}", funnel=True)
            self.assertEqual(salida["codigo"], 404, ruta)

    def test_ningun_nombre_sale_en_la_respuesta_publica(self):
        memoria.apuntar_llamada("+34600111222", "Marta")
        servidor.Comun.config_telefono = {"token": "secreto", "voz": "Polly.Lucia"}
        salida = self.peticion(servidor.Telefono, "do_GET", "/panel/datos")
        self.assertNotIn(b"Marta", salida["cuerpo"])
        self.assertNotIn(b"600111222", salida["cuerpo"])


class TestLaVistaEnTexto(CasoPanel):
    def test_el_main_no_revienta_y_enseña_el_dia(self):
        import contextlib
        self.reservar()
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = panel.main([])
        self.assertEqual(codigo, 0)
        self.assertIn("Peluquer", salida.getvalue())


class TestDondeGuardaLosDatos(unittest.TestCase):
    def test_el_panel_no_escribe_nada_por_mirarlo(self):
        # Mirar el día no puede cambiar el día. Sin esto, refrescar la pantalla
        # cada minuto tocaría ficheros mientras entra una llamada.
        entorno.aislar(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        negocio = negocios.cargar("peluqueria")
        antes = sorted(p.name for p in Path(avisos.raiz()).glob("*"))
        panel.vista(negocio, ahora=VIERNES)
        self.assertEqual(sorted(p.name for p in Path(avisos.raiz()).glob("*")), antes)


if __name__ == "__main__":
    unittest.main()
