"""Pruebas de que la organización del repo sigue siendo la que se decidió.

Un repo se desordena solo: se añade un fichero a la raíz «por ahora» y a
los seis meses hay veintiséis. Esto lo vigila, y sobre todo vigila las dos
cosas que al moverlo se rompieron de verdad y no daban la cara:

- Las rutas calculadas desde `__file__`. Al bajar un nivel, `parent` dejó
  de ser la raíz del repo, y `.env`, `negocios/` y `datos/` se buscaban en
  la carpeta del paquete. Nada revienta: simplemente no encuentra nada.
- Los imports dinámicos (`__import__("rag")`), que ningún renombrado
  automático ve porque para el código son una cadena de texto.
"""

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

PAQUETES = {"telefono", "mente", "negocio", "guardado", "dueno"}


class TestLaEstructura(unittest.TestCase):
    def test_no_hay_modulos_sueltos_en_la_raiz(self):
        sueltos = [f.name for f in RAIZ.glob("*.py")]
        self.assertEqual(sueltos, [], "cada módulo va en su carpeta")

    def test_cada_paquete_existe_y_dice_para_que_es(self):
        for paquete in PAQUETES:
            with self.subTest(paquete=paquete):
                init = RAIZ / paquete / "__init__.py"
                self.assertTrue(init.exists(), f"falta {paquete}/__init__.py")
                self.assertTrue(init.read_text(encoding="utf-8").strip().startswith('"""'),
                                f"{paquete} no explica para qué es")

    def test_no_hay_un_paquete_que_se_llame_datos(self):
        # `datos/` está en el .gitignore: es donde viven los datos de verdad.
        # Un paquete con ese nombre no se subiría, y dar con eso cuesta.
        self.assertFalse((RAIZ / "datos" / "__init__.py").exists())


class TestLoQueSeRompeAlMover(unittest.TestCase):
    def modulos(self):
        for paquete in PAQUETES:
            yield from (RAIZ / paquete).glob("*.py")

    def test_las_rutas_desde_file_cuentan_el_nivel_de_mas(self):
        # Un módulo dentro de un paquete está a dos niveles de la raíz.
        mal = []
        for fichero in self.modulos():
            for numero, linea in enumerate(
                    fichero.read_text(encoding="utf-8").splitlines(), 1):
                if "__file__" in linea and ".parent" in linea \
                        and ".parent.parent" not in linea:
                    mal.append(f"{fichero.relative_to(RAIZ)}:{numero}")
        self.assertEqual(mal, [], "esto busca en la carpeta del paquete, no en la raíz")

    def test_no_quedan_imports_dinamicos_por_nombre(self):
        # `__import__("rag")` sobrevive a cualquier renombrado y se cae
        # luego, en tiempo de ejecución, cuando ya has colgado el teléfono.
        mal = []
        for fichero in self.modulos():
            texto = fichero.read_text(encoding="utf-8")
            for cadena in re.findall(r'__import__\(["\'](\w+)["\']\)', texto):
                if cadena not in ("threading",):     # stdlib, no se mueve
                    mal.append(f"{fichero.relative_to(RAIZ)}: __import__({cadena!r})")
        self.assertEqual(mal, [])

    def test_la_raiz_del_repo_se_encuentra_desde_dentro(self):
        # La prueba de verdad: que los sitios que leen ficheros los vean.
        import os
        from dueno import avisar
        from guardado import datos
        from mente import conocimiento
        from negocio import negocio as negocios
        self.assertEqual(avisar.RAIZ, RAIZ)
        self.assertTrue(negocios.carpeta_negocios().is_dir(),
                        negocios.carpeta_negocios())
        # Sin variable puesta, las dos carpetas cuelgan de la raíz del repo.
        for modulo, cual in ((conocimiento, "conocimiento"), (datos, "datos")):
            with self.subTest(modulo=cual):
                antes = os.environ.pop(modulo.VARIABLE, None)
                try:
                    donde = modulo.carpeta() if cual == "conocimiento" else modulo.raiz()
                    self.assertEqual(donde, RAIZ / cual)
                finally:
                    if antes is not None:
                        os.environ[modulo.VARIABLE] = antes


class TestLosPuntosDeEntrada(unittest.TestCase):
    """Lo que arranca el Makefile y systemd tiene que existir de verdad."""

    def ordenes_del_makefile(self):
        texto = (RAIZ / "Makefile").read_text(encoding="utf-8")
        return set(re.findall(r"\$\(PY\) -m ([a-z_]+\.[a-z_]+)", texto))

    def test_cada_orden_del_makefile_apunta_a_un_modulo_que_existe(self):
        for orden in self.ordenes_del_makefile():
            paquete, modulo = orden.split(".")
            with self.subTest(orden=orden):
                self.assertTrue((RAIZ / paquete / f"{modulo}.py").exists(),
                                f"«make» llama a {orden} y no está")

    def test_ningun_servicio_llama_a_un_fichero_suelto(self):
        for unidad in RAIZ.glob("*.service.in"):
            texto = unidad.read_text(encoding="utf-8")
            sueltos = re.findall(r"python\S* ([a-z_]+)\.py", texto)
            with self.subTest(unidad=unidad.name):
                self.assertEqual(sueltos, [], "usa «python -m paquete.modulo»")

    def test_los_servicios_se_paran_en_la_raiz_del_repo(self):
        # `python -m` necesita que el directorio de trabajo sea la raíz. Sin
        # WorkingDirectory el servicio arrancaría y no encontraría nada.
        for unidad in RAIZ.glob("*.service.in"):
            with self.subTest(unidad=unidad.name):
                self.assertIn("WorkingDirectory=",
                              unidad.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
