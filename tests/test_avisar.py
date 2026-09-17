"""Pruebas de avisar.py — que el aviso llegue, y que no se de por llegado antes."""

import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

from dueno import avisar  # noqa: E402
from hugin.guardado import avisos  # noqa: E402

CONFIG = {"token": "t", "chat": "c", "tipos": ("cita", "fallo")}


class Buzon:
    """Un Telegram de mentira: guarda lo que le mandan, o falla como se le diga."""

    def __init__(self, fallar_markdown=False, fallar_todo=False):
        self.mensajes = []
        self.fallar_markdown, self.fallar_todo = fallar_markdown, fallar_todo

    def __call__(self, token, chat, texto, markdown):
        if self.fallar_todo:
            raise urllib.error.URLError("sin red")
        if markdown and self.fallar_markdown:
            raise urllib.error.HTTPError("u", 400, "Bad Request", {}, None)
        self.mensajes.append((texto, markdown))


class CasoAvisar(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ruta = Path(self._tmp.name) / "avisos.json"

    def apuntar(self, tipo, texto):
        return avisos.registrar(tipo, texto, ruta=self.ruta)


class TestEnviar(unittest.TestCase):
    def test_manda_en_markdown(self):
        buzon = Buzon()
        self.assertTrue(avisar.enviar("hola", mandar=buzon, config=CONFIG))
        self.assertEqual(buzon.mensajes, [("hola", True)])

    def test_si_telegram_rechaza_el_markdown_reenvia_plano(self):
        # Un `_` en lo que dijo un cliente rompe el Markdown. Antes que perder
        # el aviso, se manda tal cual.
        buzon = Buzon(fallar_markdown=True)
        self.assertTrue(avisar.enviar("cita_rara", mandar=buzon, config=CONFIG))
        self.assertEqual(buzon.mensajes, [("cita_rara", False)])

    def test_sin_red_devuelve_false_y_no_revienta(self):
        self.assertFalse(avisar.enviar("hola", mandar=Buzon(fallar_todo=True), config=CONFIG))

    def test_sin_configurar_no_hace_nada(self):
        entorno_real = dict(os.environ)
        for clave in ("GJALLARHORN_TELEGRAM_TOKEN", "GJALLARHORN_TELEGRAM_CHAT"):
            os.environ.pop(clave, None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(entorno_real)))
        real = avisar._leer_env
        avisar._leer_env = lambda *a, **k: None       # ni un .env de verdad
        self.addCleanup(setattr, avisar, "_leer_env", real)
        self.assertIsNone(avisar.configuracion())
        self.assertFalse(avisar.enviar("hola", mandar=Buzon()))


class TestAvisarNuevos(CasoAvisar):
    def test_manda_los_pendientes_de_los_tipos_configurados(self):
        self.apuntar("cita", "Reservada: tinte el jueves")
        self.apuntar("tarifa", "Tinte → 45 €")            # no esta en tipos
        buzon = Buzon()
        n = avisar.avisar_nuevos(mandar=buzon, config=CONFIG, ruta=self.ruta)
        self.assertEqual(n, 1)
        self.assertIn("tinte el jueves", buzon.mensajes[0][0])
        self.assertNotIn("45 €", buzon.mensajes[0][0])

    def test_lo_mandado_queda_visto_y_no_se_repite(self):
        self.apuntar("cita", "una")
        avisar.avisar_nuevos(mandar=Buzon(), config=CONFIG, ruta=self.ruta)
        self.assertEqual(avisar.avisar_nuevos(mandar=Buzon(), config=CONFIG, ruta=self.ruta), 0)

    def test_si_no_llega_no_se_marca_visto(self):
        # Lo importante: un fallo de red no puede hacer desaparecer un aviso.
        self.apuntar("cita", "una")
        n = avisar.avisar_nuevos(mandar=Buzon(fallar_todo=True), config=CONFIG, ruta=self.ruta)
        self.assertEqual(n, 0)
        self.assertEqual(len(avisos.listar(solo_nuevos=True, ruta=self.ruta)), 1)

    def test_los_avisos_ya_vistos_no_se_reenvian(self):
        a = self.apuntar("cita", "vieja")
        avisos.marcar_vistos([a["id"]], ruta=self.ruta)
        self.assertEqual(avisar.avisar_nuevos(mandar=Buzon(), config=CONFIG, ruta=self.ruta), 0)


class TestElEnv(unittest.TestCase):
    def test_lee_un_env_sin_pisar_el_entorno(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("# comentario\nPRUEBA_GJ_A='uno'\nPRUEBA_GJ_B=dos\n", encoding="utf-8")
            os.environ["PRUEBA_GJ_B"] = "ya-estaba"
            self.addCleanup(os.environ.pop, "PRUEBA_GJ_A", None)
            self.addCleanup(os.environ.pop, "PRUEBA_GJ_B", None)
            avisar._leer_env(env)
        self.assertEqual(os.environ["PRUEBA_GJ_A"], "uno")
        self.assertEqual(os.environ["PRUEBA_GJ_B"], "ya-estaba")


if __name__ == "__main__":
    unittest.main()
