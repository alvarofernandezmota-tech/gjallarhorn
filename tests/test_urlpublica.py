"""Pruebas de la URL que se pega en el panel del proveedor.

Parece una tontería y no lo es: mientras esto imprimía
`https://<esta-maquina>.<tailnet>.ts.net/...`, alguien tenía que traducir
el hueco a mano antes de pegarlo, y pegar el `<...>` tal cual es un error
que ya ha pasado. Una URL que no se puede copiar entera no está terminada.

Lo otro que se vigila: cuando de verdad no se puede saber, que lo diga.
Inventarse un nombre de máquina sería mucho peor que el hueco.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import urlpublica  # noqa: E402


class CasoURL(unittest.TestCase):
    def responder(self, salida=b"", codigo=0, revienta=None):
        """Pone un `tailscale` de mentira que contesta lo que se le diga."""
        def falso(*_, **__):
            if revienta:
                raise revienta
            return subprocess.CompletedProcess([], codigo, salida, b"")
        antes = subprocess.run
        subprocess.run = falso
        self.addCleanup(lambda: setattr(subprocess, "run", antes))

    def con_maquina(self, nombre):
        self.responder(json.dumps({"Self": {"DNSName": nombre}}).encode())


class TestCuandoSeSabe(CasoURL):
    def test_la_url_sale_entera_y_sin_huecos(self):
        self.con_maquina("acer.tail1234.ts.net.")
        self.assertEqual(urlpublica.base(), "https://acer.tail1234.ts.net")
        self.assertNotIn("<", urlpublica.base())

    def test_el_punto_final_del_dns_no_va_en_la_url(self):
        # tailscale devuelve el DNS con el punto raíz. En una URL sobra.
        self.con_maquina("acer.tail1234.ts.net.")
        self.assertFalse(urlpublica.base().endswith("."))

    def test_las_dos_urls_del_proveedor(self):
        self.con_maquina("acer.tail1234.ts.net.")
        dicho = self.imprimir()
        self.assertIn("https://acer.tail1234.ts.net/telefono/entrada", dicho)
        self.assertIn("https://acer.tail1234.ts.net/telefono/fin", dicho)
        self.assertNotIn("<esta-maquina>", dicho)

    def imprimir(self, *argumentos):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            urlpublica.main(list(argumentos) or ["--para-el-proveedor"])
        return salida.getvalue()


class TestCuandoNoSeSabe(CasoURL):
    def imprimir(self):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            urlpublica.main(["--para-el-proveedor"])
        return salida.getvalue()

    def test_sin_tailscale_instalado_no_revienta(self):
        self.responder(revienta=FileNotFoundError("no such file: tailscale"))
        self.assertIsNone(urlpublica.nombre_de_esta_maquina())
        self.assertEqual(urlpublica.base(), urlpublica.GENERICA)

    def test_si_tarda_demasiado_no_se_queda_colgado(self):
        self.responder(revienta=subprocess.TimeoutExpired("tailscale", 5))
        self.assertIsNone(urlpublica.nombre_de_esta_maquina())

    def test_si_contesta_basura_no_revienta(self):
        self.responder(b"esto no es json")
        self.assertIsNone(urlpublica.nombre_de_esta_maquina())

    def test_si_sale_con_error_no_se_usa_lo_que_diga(self):
        self.responder(json.dumps({"Self": {"DNSName": "algo"}}).encode(), codigo=1)
        self.assertIsNone(urlpublica.nombre_de_esta_maquina())

    def test_si_no_viene_el_nombre_no_se_inventa(self):
        for vacio in ({}, {"Self": {}}, {"Self": {"DNSName": ""}},
                      {"Self": {"DNSName": "   "}}):
            with self.subTest(json=vacio):
                self.responder(json.dumps(vacio).encode())
                self.assertIsNone(urlpublica.nombre_de_esta_maquina())

    def test_se_avisa_de_que_son_huecos_y_no_parte_de_la_url(self):
        self.responder(revienta=FileNotFoundError())
        dicho = self.imprimir()
        self.assertIn("<esta-maquina>", dicho)
        self.assertIn("son huecos", dicho)


if __name__ == "__main__":
    unittest.main()
