"""Pruebas de telefonia.py — el número de verdad, sin número.

El proveedor no está: se le imita con los formularios que mandaría. Lo que se
vigila es lo que puede salir caro con un webhook público: que nadie sin firma
hable con esto, que dos llamadas a la vez no se mezclen, y que colgar apunte
en qué quedó.
"""

import base64
import hashlib
import hmac
import io
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

from guardado import avisos  # noqa: E402
from negocio import negocio as negocios  # noqa: E402
from telefono import servidor  # noqa: E402
from telefono import telefonia  # noqa: E402

TURNO = "https://maquina.tailnet.ts.net/telefono/turno"


def firmar(token, url, campos):
    base = url + "".join(k + campos[k] for k in sorted(campos))
    return base64.b64encode(hmac.new(token.encode(), base.encode(), hashlib.sha1).digest()).decode()


class CasoCentralita(unittest.TestCase):
    def setUp(self):
        entorno.aislar(self)
        self.negocio = negocios.cargar("peluqueria")
        self.centralita = telefonia.Centralita(self.negocio)

    def llamar(self, sid, numero="+34600000001"):
        return self.centralita.entrada({"CallSid": sid, "From": numero}, TURNO)

    def decir(self, sid, frase):
        return self.centralita.turno({"CallSid": sid, "SpeechResult": frase}, TURNO)


class TestLaFirma(unittest.TestCase):
    def test_una_firma_correcta_pasa(self):
        campos = {"CallSid": "CA1", "From": "+34600", "SpeechResult": "hola"}
        firma = firmar("secreto", TURNO, campos)
        self.assertTrue(telefonia.firma_valida("secreto", TURNO, campos, firma))

    def test_sin_firma_o_con_otra_no(self):
        campos = {"CallSid": "CA1"}
        self.assertFalse(telefonia.firma_valida("secreto", TURNO, campos, None))
        self.assertFalse(telefonia.firma_valida("secreto", TURNO, campos, "AAAA"))
        self.assertFalse(telefonia.firma_valida("otro", TURNO, campos, firmar("secreto", TURNO, campos)))

    def test_cambiar_un_campo_invalida_la_firma(self):
        campos = {"CallSid": "CA1", "SpeechResult": "cita"}
        firma = firmar("secreto", TURNO, campos)
        campos["SpeechResult"] = "cita para un tinte"
        self.assertFalse(telefonia.firma_valida("secreto", TURNO, campos, firma))


class TestLaLlamada(CasoCentralita):
    def test_al_entrar_saluda_y_escucha(self):
        xml = self.llamar("CA1")
        self.assertIn("<Gather", xml)
        self.assertIn("asistente automático", xml)     # el aviso legal, siempre
        self.assertIn(f'action="{TURNO}"', xml)

    def test_lo_que_dice_se_contesta_y_se_sigue_escuchando(self):
        self.llamar("CA1")
        xml = self.decir("CA1", "cuánto vale un tinte")
        self.assertIn("45 euros", xml)     # se lee en voz alta: euros, no €
        self.assertNotIn("€", xml)
        self.assertIn("<Gather", xml)

    def test_la_despedida_cuelga(self):
        self.llamar("CA1")
        self.decir("CA1", "cuánto vale un tinte")
        xml = self.decir("CA1", "gracias, adiós")
        self.assertIn("<Hangup/>", xml)
        self.assertNotIn("No tengo ese servicio", xml)   # el fallo que salió al probarlo

    def test_dos_llamadas_a_la_vez_no_se_mezclan(self):
        self.llamar("CA1")
        self.llamar("CA2", "+34600000002")
        self.decir("CA1", "cita para un tinte")
        self.decir("CA2", "cita para unas mechas")
        self.assertEqual(self.centralita._llamadas["CA1"].cita.servicio, "Tinte")
        self.assertEqual(self.centralita._llamadas["CA2"].cita.servicio, "Mechas")

    def test_el_silencio_se_repregunta_una_vez_y_luego_se_cuelga(self):
        self.llamar("CA1")
        primero = self.centralita.turno({"CallSid": "CA1", "SpeechResult": ""}, TURNO)
        self.assertIn("no le he oído", primero.lower())
        self.assertIn("<Gather", primero)
        segundo = self.centralita.turno({"CallSid": "CA1", "SpeechResult": ""}, TURNO, silencio=True)
        self.assertIn("<Hangup/>", segundo)

    def test_un_turno_sin_entrada_previa_no_cuelga(self):
        # Reinicio del servidor a mitad de llamada: se abre sobre la marcha.
        xml = self.decir("CA9", "qué horario tenéis")
        self.assertIn("Lunes cerrado", xml)

    def test_lo_que_se_dice_va_escapado_en_el_xml(self):
        # Un «<» o un «&» en una frase de frases.toml romperia el XML entero y
        # el proveedor colgaria con un error de aplicacion.
        self.assertEqual(telefonia._decir("A & B <C>", "V"),
                         '<Say voice="V" language="es-ES">A &amp; B &lt;C&gt;</Say>')


class TestColgarYRecordar(CasoCentralita):
    def test_al_terminar_se_apunta_en_que_quedo(self):
        self.llamar("CA1")
        self.decir("CA1", "cita para un tinte")
        self.decir("CA1", "el jueves")
        quedo = self.centralita.fin({"CallSid": "CA1"})
        self.assertIn("a medias", quedo)
        self.assertNotIn("CA1", self.centralita._llamadas)

    def test_quien_dio_su_nombre_es_reconocido_la_proxima_vez(self):
        self.llamar("CA1", "+34600000007")
        self.decir("CA1", "cita para un corte de caballero")
        self.decir("CA1", "el jueves")
        self.decir("CA1", "a las diez de la mañana")
        self.decir("CA1", "me llamo Marta")
        self.centralita.fin({"CallSid": "CA1"})

        xml = self.llamar("CA2", "+34600000007")
        self.assertIn("Hola, Marta", xml)
        self.assertEqual(self.centralita._llamadas["CA2"].nombre, "Marta")
        self.assertEqual(telefonia.cliente("+34600000007").llamadas, 1)

    def test_sin_nombre_no_se_recuerda_nada(self):
        self.llamar("CA1", "+34600000008")
        self.decir("CA1", "qué horario tenéis")
        self.centralita.fin({"CallSid": "CA1"})
        self.assertIsNone(telefonia.cliente("+34600000008"))

    def test_terminar_una_llamada_desconocida_no_revienta(self):
        self.assertIsNone(self.centralita.fin({"CallSid": "nunca-existio"}))

    def test_cada_llamada_deja_un_aviso(self):
        antes = len(avisos.listar())
        self.llamar("CA1", "+34600000009")
        self.assertEqual(len(avisos.listar()), antes + 1)
        self.assertIn("+34600000009", avisos.listar()[0]["texto"])


class CasoHandler(unittest.TestCase):
    """Monta un handler a mano y le mete una petición, sin abrir sockets."""

    def setUp(self):
        servidor.Comun.negocio = negocios.cargar("peluqueria")
        servidor.Comun.centralita = None
        servidor.Comun.config_telefono = None
        servidor.Comun.transcriptor = None
        servidor.Comun.locutor = None
        servidor.Comun.conversacion = None

    def con_telefono(self):
        servidor.Comun.config_telefono = {"token": "secreto", "voz": "Polly.Lucia"}
        servidor.Comun.centralita = telefonia.Centralita(servidor.Comun.negocio)

    def peticion(self, clase, metodo, ruta, campos=None, firma=None,
                 host="maquina.tailnet.ts.net", funnel=False, cabeceras=None):
        from urllib.parse import urlencode
        cuerpo = urlencode(campos or {}).encode()
        h = clase.__new__(clase)
        h.headers = {"Content-Length": str(len(cuerpo)), "Host": host,
                     "X-Forwarded-Proto": "https"}
        if firma:
            h.headers["X-Twilio-Signature"] = firma
        h.headers.update(cabeceras or {})
        if funnel:
            h.headers["Tailscale-Funnel-Request"] = "?1"
        h.path = ruta
        h.rfile = io.BytesIO(cuerpo)
        h.client_address = ("127.0.0.1", 0)
        h.request_version = "HTTP/1.1"
        h.close_connection = False
        salida = {}
        h._responder = lambda codigo, cuerpo, tipo: salida.update(codigo=codigo, cuerpo=cuerpo)
        getattr(h, metodo)()
        return salida


class TestElWebhookEnElServidor(CasoHandler):
    """Lo que ve el proveedor: 404 sin configurar, 403 sin firma, XML con ella."""

    def webhook(self, ruta="/telefono/entrada", campos=None, firma=None):
        return self.peticion(servidor.Telefono, "do_POST", ruta,
                             campos or {"CallSid": "CA1"}, firma)

    def test_sin_configurar_es_404(self):
        self.assertEqual(self.webhook()["codigo"], 404)

    def test_sin_firma_es_403_y_queda_constancia_una_vez(self):
        # Una sola anotación por arranque, no una por golpe: desde un puerto
        # público, un aviso por petición es dejar que cualquiera engorde el
        # fichero de datos del negocio sin límite.
        servidor.Comun._firmas_malas = 0
        self.con_telefono()
        antes = len(avisos.listar())
        for _ in range(5):
            self.assertEqual(self.webhook()["codigo"], 403)
        self.assertEqual(len(avisos.listar()), antes + 1)
        self.assertIn("sin firma válida", avisos.listar()[0]["texto"])
        self.assertEqual(servidor.Comun._firmas_malas, 5)

    def test_con_firma_contesta_twiml(self):
        self.con_telefono()
        campos = {"CallSid": "CA1", "From": "+34600"}
        url = "https://maquina.tailnet.ts.net/telefono/entrada"
        salida = self.webhook(campos=campos, firma=firmar("secreto", url, campos))
        self.assertEqual(salida["codigo"], 200)
        self.assertIn(b"<Gather", salida["cuerpo"])

    def test_las_rutas_del_telefono_se_reconocen_con_y_sin_consulta(self):
        for ruta in ("/telefono/entrada", "/telefono/turno", "/telefono/turno?silencio=1", "/telefono/fin"):
            self.assertTrue(telefonia.RUTAS.match(ruta), ruta)
        self.assertFalse(telefonia.RUTAS.match("/telefono/otra"))
        self.assertFalse(telefonia.RUTAS.match("/hablar"))


class TestElPuertoPublicoNoSirveLaDemo(CasoHandler):
    """La separación de verdad: el puerto que se publica no conoce la demo.

    No depende de mirar una cabecera ni de confiar en Tailscale. `Telefono` no
    tiene ruta para `/`, `/hablar` ni `/colgar`, así que publicarlo no publica
    la demo aunque alguien se equivoque de puerto en el `funnel`.
    """

    def test_la_pagina_no_existe_en_el_puerto_publico(self):
        self.con_telefono()
        self.assertEqual(self.peticion(servidor.Telefono, "do_GET", "/")["codigo"], 404)
        self.assertEqual(self.peticion(servidor.Telefono, "do_GET", "/index.html")["codigo"], 404)

    def test_hablar_y_colgar_tampoco(self):
        self.con_telefono()
        for ruta in ("/hablar", "/colgar"):
            salida = self.peticion(servidor.Telefono, "do_POST", ruta, {"texto": "hola"})
            self.assertEqual(salida["codigo"], 404, ruta)

    def test_el_puerto_publico_no_toca_la_agenda_ni_whisper(self):
        # Lo caro de que /hablar estuviera abierto: arranca Whisper con el
        # audio que le manden y reserva en la agenda de un negocio real.
        self.con_telefono()
        antes = len(avisos.listar())
        self.peticion(servidor.Telefono, "do_POST", "/hablar", {"texto": "quiero cita"})
        self.assertEqual(len(avisos.listar()), antes)


class TestLaDemoNoAtiendeAInternet(CasoHandler):
    """Segunda cerradura: si alguien publica el puerto de la demo, no sirve.

    Tailscale marca con `Tailscale-Funnel-Request` lo que entra de internet.
    Esto no es de lo que depende la separación —para eso están los dos
    puertos— pero para el error de publicar el puerto equivocado.
    """

    def test_con_la_marca_de_funnel_la_pagina_da_404(self):
        self.assertEqual(
            self.peticion(servidor.Recepcion, "do_GET", "/", funnel=True)["codigo"], 404)

    def test_con_la_marca_de_funnel_hablar_da_404(self):
        salida = self.peticion(servidor.Recepcion, "do_POST", "/hablar",
                               {"texto": "hola"}, funnel=True)
        self.assertEqual(salida["codigo"], 404)

    def test_sin_la_marca_la_pagina_se_sirve_normal(self):
        salida = self.peticion(servidor.Recepcion, "do_GET", "/")
        self.assertEqual(salida["codigo"], 200)
        self.assertIn("peluquería".encode(), salida["cuerpo"])

    def test_el_webhook_no_vive_en_el_puerto_de_la_demo(self):
        # Si estuviera en los dos, publicar cualquiera publicaria el webhook,
        # y la demo con el.
        self.con_telefono()
        salida = self.peticion(servidor.Recepcion, "do_POST", "/telefono/entrada",
                               {"CallSid": "CA1"})
        self.assertEqual(salida["codigo"], 404)


if __name__ == "__main__":
    unittest.main()


class TestElWebhookConTelnyx(CasoHandler):
    """La misma puerta, con el otro proveedor.

    Telnyx firma con Ed25519 y clave pública, no con el HMAC del Auth Token
    de Twilio. Estas pruebas van por el servidor entero —no por la función
    de la firma— porque lo que se puede romper sin enterarse está en medio:
    que el cuerpo que se verifica sea el crudo que llegó y no uno vuelto a
    montar desde los campos, y que la cabecera elija el validador bueno.
    """

    def setUp(self):
        super().setUp()
        import base64
        import ed25519_de_mentira as telnyx_falso
        self.falso = telnyx_falso
        self.semilla, publica = telnyx_falso.clave(b"la peluqueria")
        self.publica = base64.b64encode(publica).decode("ascii")
        servidor.Comun.config_telefono = {"token": "", "clave_publica": self.publica,
                                          "voz": "Polly.Lucia"}
        servidor.Comun.centralita = telefonia.Centralita(servidor.Comun.negocio)

    def firmado(self, campos, marca=None, semilla=None):
        """Las cabeceras que mandaría Telnyx para ese cuerpo exacto."""
        import base64
        import time
        from urllib.parse import urlencode
        marca = marca or str(int(time.time()))
        cuerpo = urlencode(campos).encode()
        firma = self.falso.firmar(semilla or self.semilla,
                                  marca.encode("utf-8") + b"|" + cuerpo)
        return {telefonia.CABECERA_TELNYX: base64.b64encode(firma).decode("ascii"),
                telefonia.CABECERA_MARCA_TELNYX: marca}

    def webhook(self, campos=None, cabeceras=None, ruta="/telefono/entrada"):
        campos = campos or {"CallSid": "CA1", "From": "+34600111222"}
        return self.peticion(servidor.Telefono, "do_POST", ruta, campos,
                             cabeceras=cabeceras if cabeceras is not None
                             else self.firmado(campos))

    def test_una_llamada_bien_firmada_contesta_twiml(self):
        salida = self.webhook()
        self.assertEqual(salida["codigo"], 200)
        self.assertIn(b"<Response>", salida["cuerpo"])
        self.assertIn("peluquería".encode(), salida["cuerpo"])

    def test_sin_firma_es_403(self):
        self.assertEqual(self.webhook(cabeceras={})["codigo"], 403)

    def test_con_la_firma_de_otra_clave_es_403(self):
        otra, _ = self.falso.clave(b"otro negocio")
        campos = {"CallSid": "CA1", "From": "+34600111222"}
        self.assertEqual(
            self.webhook(campos, self.firmado(campos, semilla=otra))["codigo"], 403)

    def test_firmar_un_cuerpo_y_mandar_otro_es_403(self):
        # Lo que pasaría si se verificara sobre los campos vueltos a montar
        # en vez de sobre los bytes que llegaron.
        firmadas = self.firmado({"CallSid": "CA1", "From": "+34600111222"})
        self.assertEqual(
            self.webhook({"CallSid": "CA1", "From": "+34600999999"}, firmadas)["codigo"],
            403)

    def test_una_peticion_vieja_grabada_es_403(self):
        import time
        campos = {"CallSid": "CA1", "From": "+34600111222"}
        vieja = self.firmado(campos, marca=str(int(time.time()) - 3600))
        self.assertEqual(self.webhook(campos, vieja)["codigo"], 403)

    def test_la_cabecera_de_twilio_con_clave_de_telnyx_es_403(self):
        # Ni se valida «con lo que haya»: sin token de Twilio puesto, una
        # petición que dice venir de Twilio no entra.
        campos = {"CallSid": "CA1"}
        self.assertEqual(
            self.peticion(servidor.Telefono, "do_POST", "/telefono/entrada",
                          campos, firma="loquesea")["codigo"], 403)

    def test_la_llamada_entera_por_telnyx(self):
        # Entrada, un turno hablando y el fin: los tres firmados.
        salida = self.webhook()
        self.assertEqual(salida["codigo"], 200)
        campos = {"CallSid": "CA1", "SpeechResult": "¿cuánto vale un tinte?"}
        turno = self.webhook(campos, self.firmado(campos), ruta="/telefono/turno")
        self.assertEqual(turno["codigo"], 200)
        self.assertIn(b"45", turno["cuerpo"])
        fin = {"CallSid": "CA1"}
        self.assertEqual(
            self.webhook(fin, self.firmado(fin), ruta="/telefono/fin")["codigo"], 200)
