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

import entorno  # noqa: E402,F401

import avisos  # noqa: E402
import negocio as negocios  # noqa: E402
import servidor  # noqa: E402
import telefonia  # noqa: E402

TURNO = "https://maquina.tailnet.ts.net/telefono/turno"


def firmar(token, url, campos):
    base = url + "".join(k + campos[k] for k in sorted(campos))
    return base64.b64encode(hmac.new(token.encode(), base.encode(), hashlib.sha1).digest()).decode()


class CasoCentralita(unittest.TestCase):
    def setUp(self):
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
        self.assertIn("45 €", xml)
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
        self.assertEqual(telefonia.cliente("+34600000007")["llamadas"], 1)

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


class TestElWebhookEnElServidor(unittest.TestCase):
    """Lo que ve el proveedor: 404 sin configurar, 403 sin firma, XML con ella."""

    def peticion(self, ruta, campos, firma=None, host="maquina.tailnet.ts.net"):
        from urllib.parse import urlencode
        cuerpo = urlencode(campos).encode()
        h = servidor.Recepcion.__new__(servidor.Recepcion)
        cab = {"Content-Length": str(len(cuerpo)), "Host": host, "X-Forwarded-Proto": "https"}
        if firma:
            cab["X-Twilio-Signature"] = firma
        h.headers = cab
        h.path = ruta
        h.rfile = io.BytesIO(cuerpo)
        h.client_address = ("127.0.0.1", 0)
        h.request_version = "HTTP/1.1"
        h.close_connection = False
        salida = {}
        h._responder = lambda codigo, cuerpo, tipo: salida.update(codigo=codigo, cuerpo=cuerpo)
        h._telefono()
        return salida

    def setUp(self):
        servidor.Recepcion.negocio = negocios.cargar("peluqueria")
        servidor.Recepcion.centralita = None
        servidor.Recepcion.config_telefono = None

    def test_sin_configurar_es_404(self):
        self.assertEqual(self.peticion("/telefono/entrada", {"CallSid": "CA1"})["codigo"], 404)

    def test_sin_firma_es_403_y_queda_aviso(self):
        servidor.Recepcion.config_telefono = {"token": "secreto", "voz": "Polly.Lucia"}
        servidor.Recepcion.centralita = telefonia.Centralita(servidor.Recepcion.negocio)
        salida = self.peticion("/telefono/entrada", {"CallSid": "CA1"})
        self.assertEqual(salida["codigo"], 403)
        self.assertIn("firma mala", avisos.listar()[0]["texto"])

    def test_con_firma_contesta_twiml(self):
        servidor.Recepcion.config_telefono = {"token": "secreto", "voz": "Polly.Lucia"}
        servidor.Recepcion.centralita = telefonia.Centralita(servidor.Recepcion.negocio)
        campos = {"CallSid": "CA1", "From": "+34600"}
        url = "https://maquina.tailnet.ts.net/telefono/entrada"
        salida = self.peticion("/telefono/entrada", campos, firma=firmar("secreto", url, campos))
        self.assertEqual(salida["codigo"], 200)
        self.assertIn(b"<Gather", salida["cuerpo"])

    def test_las_rutas_del_telefono_se_reconocen_con_y_sin_consulta(self):
        for ruta in ("/telefono/entrada", "/telefono/turno", "/telefono/turno?silencio=1", "/telefono/fin"):
            self.assertTrue(telefonia.RUTAS.match(ruta), ruta)
        self.assertFalse(telefonia.RUTAS.match("/telefono/otra"))
        self.assertFalse(telefonia.RUTAS.match("/hablar"))


if __name__ == "__main__":
    unittest.main()
