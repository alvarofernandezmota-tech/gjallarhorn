"""Pruebas de diagnostico.py — el informe que se pega una vez."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

import diagnostico  # noqa: E402


class TestElInforme(unittest.TestCase):
    def test_sale_entero_sin_modelos_ni_servicio(self):
        texto = diagnostico.informe("peluqueria", 1, corto=False)
        self.assertIn("python", texto)
        self.assertIn("negocio: Peluquería", texto)
        self.assertIn("horario: si", texto)
        self.assertIn("avisos:", texto)

    def test_el_corto_es_corto(self):
        largo = diagnostico.informe("peluqueria", 1, corto=False)
        corto = diagnostico.informe("peluqueria", 1, corto=True)
        self.assertLess(len(corto.splitlines()), len(largo.splitlines()))

    def test_un_negocio_que_no_existe_se_dice_sin_reventar(self):
        texto = diagnostico.informe("no-existe", 1, corto=False)
        self.assertIn("❌", texto)

    def test_no_lleva_ips_ni_nombre_de_maquina(self):
        # El informe se pega en sitios publicos.
        texto = diagnostico.informe("peluqueria", 1, corto=False)
        self.assertNotRegex(texto, r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
        self.assertNotIn(os.uname().nodename, texto)

    def test_un_puerto_cogido_se_ve(self):
        import socket
        s = socket.socket()
        self.addCleanup(s.close)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        self.assertTrue(diagnostico.puerto_cogido(s.getsockname()[1]))

    def test_sin_cache_de_modelos_lo_dice(self):
        real = Path.home
        with tempfile.TemporaryDirectory() as tmp:
            Path.home = staticmethod(lambda: Path(tmp))
            try:
                lineas = diagnostico.modelos()
            finally:
                Path.home = real
        self.assertIn("whisper: ningun modelo bajado", lineas)
        self.assertIn("piper: ninguna voz bajada", lineas)


if __name__ == "__main__":
    unittest.main()
