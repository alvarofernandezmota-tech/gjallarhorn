"""Que hugin siga siendo una libreria y no se vuelva media aplicacion.

Estas pruebas no miran lo que el codigo hace: miran su **forma**. Son las
unicas que se caen el dia que alguien —yo, dentro de seis meses, con prisa—
mete aqui un import de un canal porque «total, es una linea».
"""

import ast
import os
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ.parent))

import entorno  # noqa: E402,F401

from hugin.guardado import ajustes  # noqa: E402

PAQUETES = ("mente", "negocio", "guardado")

# Un canal es por donde entra la conversacion. hugin no sabe cual es, y esa
# es toda la razon de que este repo exista aparte.
CANALES = {"telefono", "dueno", "twilio", "telnyx", "signalwire", "flask"}


def modulos():
    for paquete in PAQUETES:
        yield from sorted((RAIZ / paquete).glob("*.py"))


class TestNoSabeDeNingunCanal(unittest.TestCase):
    def test_ningun_modulo_importa_un_canal(self):
        for fich in modulos():
            arbol = ast.parse(fich.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Import):
                    nombres = [a.name.split(".")[0] for a in nodo.names]
                elif isinstance(nodo, ast.ImportFrom):
                    nombres = [(nodo.module or "").split(".")[0]]
                else:
                    continue
                for nombre in nombres:
                    self.assertNotIn(
                        nombre, CANALES,
                        f"{fich.name} importa «{nombre}»: eso es un canal, y el "
                        f"cerebro no tiene que enterarse de por donde le hablan")

    def test_los_imports_de_casa_van_por_el_nombre_del_paquete(self):
        # `from mente import fechas` funciona al correr las pruebas desde la
        # raiz y se cae montado como submodulo, que es donde de verdad se usa.
        # El fallo saldria en la aplicacion, no aqui, si no se comprueba.
        for fich in modulos():
            for i, linea in enumerate(fich.read_text(encoding="utf-8").splitlines(), 1):
                pelada = linea.strip()
                for paquete in PAQUETES:
                    self.assertFalse(
                        pelada.startswith(f"from {paquete} import ")
                        or pelada == f"import {paquete}",
                        f"{fich.name}:{i} → «{pelada}»; tiene que ser hugin.{paquete}")


class TestSeUsaComoSeDice(unittest.TestCase):
    def test_la_carpeta_del_repo_es_el_paquete(self):
        # Si el repo se clona con otro nombre, `import hugin` no encuentra
        # nada. Mas vale decirlo aqui que en el arranque de la aplicacion.
        self.assertEqual(RAIZ.name, "hugin")
        self.assertTrue((RAIZ / "__init__.py").exists())

    def test_cada_paquete_existe_y_dice_para_que_es(self):
        for paquete in PAQUETES:
            inicio = RAIZ / paquete / "__init__.py"
            self.assertTrue(inicio.exists(), f"falta {paquete}/__init__.py")
            self.assertTrue(ast.get_docstring(ast.parse(inicio.read_text(encoding="utf-8"))),
                            f"{paquete}/__init__.py no dice para que es")


class TestLaSuiteNoLeeTusSecretos(unittest.TestCase):
    """Lo mismo que en gjallarhorn: correr las pruebas no carga tu .env."""

    def test_las_credenciales_no_estan_en_el_entorno(self):
        for variable in entorno.CREDENCIALES:
            self.assertIsNone(os.environ.get(variable), f"{variable} esta puesta")

    def test_el_env_de_la_suite_no_existe(self):
        self.assertFalse(ajustes.fichero().exists())

    def test_el_env_se_busca_desde_el_directorio_de_trabajo(self):
        # Nunca desde `__file__`: esta libreria vive dentro de la aplicacion
        # que la usa, y el .env es de quien despliega, no de quien programa.
        fuente = (RAIZ / "guardado" / "ajustes.py").read_text(encoding="utf-8")
        cuerpo = fuente.split("def fichero", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("Path.cwd()", cuerpo)
        self.assertNotIn("__file__", cuerpo)


if __name__ == "__main__":
    unittest.main()
