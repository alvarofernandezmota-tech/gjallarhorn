"""Pruebas del comando que lleva de un repo recién clonado a la llamada.

Lo que se vigila aquí no es que imprima bonito, es que **no deje pasar una
clave que no sirve**. Ese es el error que no da la cara: el webhook arranca
igual y luego todas las llamadas se caen con un 403, y para entonces ya le
has dado el número a alguien.

Y lo otro: que escribir en el .env sustituya en vez de añadir. Un .env con
la misma clave tres veces es exactamente cómo se llegó hasta aquí.
"""

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

import ed25519_de_mentira as telnyx  # noqa: E402

from dueno import avisar  # noqa: E402
from dueno import lanzar  # noqa: E402


def clave_de_telnyx(semilla=b"la peluqueria"):
    import base64
    return base64.b64encode(telnyx.clave(semilla)[1]).decode("ascii")


class TestQueClaveEs(unittest.TestCase):
    """El error más fácil: la API Key de Telnyx donde va la clave pública."""

    def test_la_clave_publica_de_telnyx_se_reconoce(self):
        cual = lanzar._que_clave_es(clave_de_telnyx())
        self.assertEqual(cual[0], lanzar.CLAVE_TELNYX)

    def test_el_auth_token_de_twilio_se_reconoce(self):
        cual = lanzar._que_clave_es("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")
        self.assertEqual(cual[0], lanzar.TOKEN_TWILIO)

    def test_la_api_key_de_telnyx_se_rechaza(self):
        # Es lo que hay que rechazar sí o sí: se parece a una credencial,
        # la da el mismo proveedor, y no sirve para comprobar ninguna firma.
        self.assertIsNone(lanzar._que_clave_es("KEY01973DE066A9C3C1D2E3F4A5B6C7D8"))
        self.assertIsNone(lanzar._que_clave_es("key0197_minusculas_tambien"))

    def test_el_hueco_de_una_guia_se_rechaza(self):
        for hueco in ("<tu API Key de Telnyx>", "<el token de tu proveedor>",
                      "pon-aqui-el-token"):
            with self.subTest(hueco=hueco):
                self.assertIsNone(lanzar._que_clave_es(hueco))

    def test_lo_vacio_y_lo_que_no_es_nada_se_rechaza(self):
        for nada in ("", "   ", "hola", "no se que poner aqui"):
            with self.subTest(nada=nada):
                self.assertIsNone(lanzar._que_clave_es(nada))

    def test_una_clave_a_medio_pegar_se_rechaza(self):
        entera = clave_de_telnyx()
        self.assertIsNone(lanzar._que_clave_es(entera[:20]))


class TestEscribirEnElEnv(unittest.TestCase):
    def setUp(self):
        self.env = Path(tempfile.mkdtemp()) / ".env"

    def lineas(self):
        return self.env.read_text(encoding="utf-8").splitlines()

    def test_en_un_env_que_no_existe_se_crea(self):
        self.assertEqual(avisar.poner_en_env("UNA", "1", self.env), "puesta")
        self.assertEqual(self.lineas(), ["UNA=1"])

    def test_se_sustituye_en_vez_de_anadir(self):
        avisar.poner_en_env("UNA", "vieja", self.env)
        self.assertEqual(avisar.poner_en_env("UNA", "nueva", self.env), "cambiada")
        self.assertEqual(self.lineas(), ["UNA=nueva"])

    def test_las_repetidas_de_antes_se_limpian(self):
        # El caso real: la misma clave tres veces, y con systemd gana la
        # última, así que la que acabas de poner puede no ser la que se usa.
        self.env.write_text("UNA=a\nOTRA=x\nUNA=b\nUNA=c\n", encoding="utf-8")
        avisar.poner_en_env("UNA", "buena", self.env)
        self.assertEqual(self.lineas(), ["UNA=buena", "OTRA=x"])
        self.assertEqual(avisar.repetidas_en_env(self.env), [])

    def test_lo_comentado_no_se_toca(self):
        # Un «# CLAVE=» del ejemplo es documentación, no una clave puesta.
        self.env.write_text("# UNA=lo que sea\nOTRA=x\n", encoding="utf-8")
        avisar.poner_en_env("UNA", "1", self.env)
        self.assertIn("# UNA=lo que sea", self.lineas())
        self.assertIn("UNA=1", self.lineas())

    def test_poner_lo_mismo_dos_veces_no_cambia_nada(self):
        avisar.poner_en_env("UNA", "1", self.env)
        self.assertEqual(avisar.poner_en_env("UNA", "1", self.env), "igual")
        self.assertEqual(self.lineas().count("UNA=1"), 1)

    def test_no_se_come_lo_de_los_demas(self):
        self.env.write_text("OTRA=x\nTERCERA=y\n", encoding="utf-8")
        avisar.poner_en_env("UNA", "1", self.env)
        for sigue in ("OTRA=x", "TERCERA=y", "UNA=1"):
            self.assertIn(sigue, self.lineas())

    def test_el_fichero_acaba_en_salto_de_linea(self):
        avisar.poner_en_env("UNA", "1", self.env)
        self.assertTrue(self.env.read_text(encoding="utf-8").endswith("\n"))


class TestLosPasos(unittest.TestCase):
    def setUp(self):
        entorno.aislar(self)

    def correr(self, *argumentos):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = lanzar.main(list(argumentos))
        return codigo, salida.getvalue()

    def test_sin_clave_se_para_en_el_paso_1_y_no_publica_nada(self):
        # Lo importante: no llega a tailscale. Publicar el webhook sin con
        # qué comprobar la firma sería abrirlo a cualquiera.
        import builtins
        antes = builtins.input
        builtins.input = lambda *_: ""
        self.addCleanup(lambda: setattr(builtins, "input", antes))
        codigo, dicho = self.correr("--sin-esperar")
        self.assertEqual(codigo, 1)
        self.assertIn("1.", dicho)
        self.assertNotIn("Publicado", dicho)

    def test_una_api_key_pegada_no_se_escribe(self):
        import builtins
        antes = builtins.input
        builtins.input = lambda *_: "KEY01973DE066A9C3C1D2E3F4A5B6C7D8"
        self.addCleanup(lambda: setattr(builtins, "input", antes))
        codigo, dicho = self.correr("--sin-esperar")
        self.assertEqual(codigo, 1)
        self.assertIn("no lo escribo", dicho)
        self.assertIn("clave PUBLICA", dicho)

    def test_un_negocio_que_no_existe_se_dice(self):
        codigo, dicho = self.correr("--negocio", "no-existe")
        self.assertEqual(codigo, 1)
        self.assertIn("no encuentro el negocio", dicho)


if __name__ == "__main__":
    unittest.main()


class TestBarrerLosHuecos(unittest.TestCase):
    """Quejarse de una línea muerta y dejarla ahí es dar trabajo.

    Obligaba a salir del lanzador, editar el `.env` a mano y volver a
    entrar. Y mientras siguiera puesta, `revisar` la sacaba en rojo aunque
    ya hubieras puesto la buena del otro proveedor.
    """

    def setUp(self):
        self.env = Path(tempfile.mkdtemp()) / ".env"

    def test_se_borra_el_hueco_del_ejemplo(self):
        self.env.write_text("GJALLARHORN_TELEFONO_TOKEN=<tu API Key de Telnyx>\n"
                            "GJALLARHORN_TELEGRAM_CHAT=123\n", encoding="utf-8")
        self.assertEqual(avisar.quitar_del_env("GJALLARHORN_TELEFONO_TOKEN", self.env), 1)
        self.assertEqual(self.env.read_text(encoding="utf-8").splitlines(),
                         ["GJALLARHORN_TELEGRAM_CHAT=123"])

    def test_lo_comentado_no_se_toca(self):
        # Un «# CLAVE=» del ejemplo es documentación, no una clave puesta.
        self.env.write_text("# GJALLARHORN_TELEFONO_TOKEN=\nOTRA=x\n", encoding="utf-8")
        avisar.quitar_del_env("GJALLARHORN_TELEFONO_TOKEN", self.env)
        self.assertIn("# GJALLARHORN_TELEFONO_TOKEN=",
                      self.env.read_text(encoding="utf-8"))

    def test_si_no_esta_no_pasa_nada(self):
        self.env.write_text("OTRA=x\n", encoding="utf-8")
        self.assertEqual(avisar.quitar_del_env("NO_ESTA", self.env), 0)

    def test_sin_env_no_revienta(self):
        self.assertEqual(avisar.quitar_del_env("LO_QUE_SEA", Path("/no/existe/.env")), 0)

    def test_una_credencial_de_verdad_no_se_borra_sola(self):
        # `_barrer_los_huecos` solo llama a esto para lo que es de relleno.
        # Una clave buena del proveedor que no usas se queda donde está.
        from telefono import telefonia
        self.assertFalse(telefonia.token_de_mentira(
            "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"))
