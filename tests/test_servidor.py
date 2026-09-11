"""Pruebas del servidor — el MVP en el navegador.

Contra un servidor de verdad en un puerto de verdad, no contra el handler
suelto: lo que se quiere saber es que **contesta**, no que el método se llame.

Lo que se vigila no es que sirva HTML, es que no se rompa de las formas caras:
un audio enorme, un fallo a mitad, un saludo con comillas.
"""

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

import avisos  # noqa: E402
import negocio as negocios  # noqa: E402
import servidor  # noqa: E402


class CasoServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        servidor.Recepcion.negocio = negocios.cargar("peluqueria")
        servidor.Recepcion.transcriptor = None   # modo texto
        servidor.Recepcion.locutor = None
        cls.servidor = HTTPServer(("127.0.0.1", 0), servidor.Recepcion)
        cls.puerto = cls.servidor.server_address[1]
        cls.hilo = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def url(self, ruta=""):
        return f"http://127.0.0.1:{self.puerto}{ruta}"

    def decir(self, texto):
        peticion = urllib.request.Request(
            self.url("/hablar"), data=json.dumps({"texto": texto}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(peticion, timeout=10) as r:
            return json.loads(r.read())


class TestLaPagina(CasoServidor):
    def test_sirve_la_pagina_con_el_nombre_del_negocio(self):
        with urllib.request.urlopen(self.url("/"), timeout=10) as r:
            pagina = r.read().decode("utf-8")
        self.assertIn("Peluquería", pagina)
        self.assertNotIn("{{NEGOCIO}}", pagina)
        self.assertNotIn("{{MODO}}", pagina)

    def test_el_saludo_va_como_json_y_no_rompe_el_script(self):
        # Un saludo con comillas metido a pelo en el JavaScript rompe la página
        # entera y no se ve hasta abrirla.
        anterior = servidor.Recepcion.negocio
        servidor.Recepcion.negocio = negocios.Negocio(
            nombre="Con «comillas»", ruta=anterior.ruta,
            saludo='Hola, "le atiende" un asistente automático.\nSegunda línea.',
            despedida="adiós")
        self.addCleanup(setattr, servidor.Recepcion, "negocio", anterior)
        with urllib.request.urlopen(self.url("/"), timeout=10) as r:
            pagina = r.read().decode("utf-8")
        self.assertIn(r'\"le atiende\"', pagina)
        self.assertNotIn("{{SALUDO_JSON}}", pagina)

    def test_una_ruta_que_no_existe_da_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caso:
            urllib.request.urlopen(self.url("/lo-que-sea"), timeout=10)
        self.assertEqual(caso.exception.code, 404)


class TestContesta(CasoServidor):
    def test_un_precio_sale_de_la_tabla(self):
        datos = self.decir("cuánto vale un corte de señora")
        self.assertIn("20 €", datos["dicho"])

    def test_una_cita_con_hora_ambigua_repregunta(self):
        datos = self.decir("quiero cita para un tinte el jueves a las 5")
        self.assertIn("de la tarde", datos["dicho"])

    def test_sin_texto_lo_dice_en_vez_de_contestar_cualquier_cosa(self):
        self.assertIn("No le he oído", self.decir("   ")["dicho"])

    def test_en_modo_texto_no_devuelve_audio(self):
        self.assertIsNone(self.decir("cuánto vale un tinte")["audio"])


class TestNoSeRompeCaro(CasoServidor):
    def test_un_audio_enorme_se_rechaza_en_vez_de_tragarselo(self):
        # Sin tope, cualquiera tumba el proceso mandando un fichero de un giga.
        peticion = urllib.request.Request(
            self.url("/hablar"), data=b"x" * (servidor.TOPE_AUDIO + 1),
            headers={"Content-Type": "audio/webm"})
        with self.assertRaises(urllib.error.HTTPError) as caso:
            urllib.request.urlopen(peticion, timeout=20)
        self.assertEqual(caso.exception.code, 413)

    def test_audio_en_modo_texto_avisa_y_deja_rastro(self):
        antes = len(avisos.listar())
        peticion = urllib.request.Request(
            self.url("/hablar"), data=b"no soy audio de verdad",
            headers={"Content-Type": "audio/webm"})
        with urllib.request.urlopen(peticion, timeout=10) as r:
            datos = json.loads(r.read())
        # Contesta algo en vez de reventar la conexión...
        self.assertIn("problema", datos["dicho"].lower())
        # ...y sobre todo: el fallo queda registrado. Una llamada sin rastro es
        # peor que una llamada mal contestada.
        self.assertEqual(len(avisos.listar()), antes + 1)
        self.assertEqual(avisos.listar()[0]["tipo"], "fallo")

    def test_lo_que_contesta_queda_registrado(self):
        antes = len(avisos.listar())
        self.decir("cuánto cuesta la manicura")   # no está en la tabla
        self.assertEqual(len(avisos.listar()), antes + 1)


if __name__ == "__main__":
    unittest.main()


class TestElPuertoOcupado(unittest.TestCase):
    """Arrancar dos veces es el error más común, y daba un traceback.

    `HTTPServer` levanta un `OSError` de `socketserver` que habla de bind y de
    direcciones. Lo único que hace falta saber es que ya hay uno corriendo y
    cómo matarlo, así que eso es lo que se dice.
    """

    def arrancar_en(self, puerto):
        import contextlib
        import io

        argv = sys.argv
        sys.argv = ["servidor.py", "--sin-voz", "--puerto", str(puerto)]
        salida = io.StringIO()
        try:
            with contextlib.redirect_stdout(salida):
                codigo = servidor.main()
        finally:
            sys.argv = argv
        return codigo, salida.getvalue()

    def test_lo_dice_en_vez_de_reventar(self):
        import socket

        ocupado = socket.socket()
        self.addCleanup(ocupado.close)
        ocupado.bind(("0.0.0.0", 0))
        ocupado.listen(1)
        puerto = ocupado.getsockname()[1]

        codigo, dicho = self.arrancar_en(puerto)

        self.assertEqual(codigo, 1)
        self.assertIn(str(puerto), dicho)
        self.assertIn("ocupado", dicho)
        self.assertIn("pkill", dicho)      # cómo salir del paso
        self.assertIn("--puerto", dicho)   # o cómo esquivarlo

    def test_no_anuncia_una_url_que_no_esta_sirviendo(self):
        # Antes el banner se imprimía antes de coger el puerto: salía
        # «→ http://localhost:8080» y justo debajo el traceback.
        import socket

        ocupado = socket.socket()
        self.addCleanup(ocupado.close)
        ocupado.bind(("0.0.0.0", 0))
        ocupado.listen(1)

        _, dicho = self.arrancar_en(ocupado.getsockname()[1])
        self.assertNotIn("http://localhost", dicho)
