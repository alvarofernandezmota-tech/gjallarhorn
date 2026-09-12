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

# Lo que es de **esta** aplicacion. `mente`, `negocio` y `guardado` se
# fueron al submodulo hugin, que tiene sus propias pruebas de estructura.
PAQUETES = {"telefono", "dueno"}

# El cerebro, montado como submodulo en la raiz.
HUGIN = RAIZ / "hugin"


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
        from hugin.guardado import datos
        from hugin.mente import conocimiento
        from hugin.negocio import negocio as negocios
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
        return set(re.findall(r"\$\(PY\) -m ([a-z_]+(?:\.[a-z_]+)+)", texto))

    def test_cada_orden_del_makefile_apunta_a_un_modulo_que_existe(self):
        for orden in self.ordenes_del_makefile():
            # `hugin.mente.cerebro` tiene tres tramos y `telefono.voz` dos:
            # el ultimo es el modulo y los de delante son carpetas.
            *carpetas, modulo = orden.split(".")
            with self.subTest(orden=orden):
                fichero = RAIZ.joinpath(*carpetas) / f"{modulo}.py"
                self.assertTrue(fichero.exists(),
                                f"«make» llama a {orden} y no está")
                # Que exista no basta: `python -m` sobre un modulo sin
                # `__main__` no hace nada y sale con 0, o sea que el Makefile
                # «funciona» y no ha pasado nada. Le paso a `recepcion.py`
                # cuando su main() se mudo a telefono/demo.py.
                self.assertIn("__main__", fichero.read_text(encoding="utf-8"),
                              f"«make» llama a {orden} y ese módulo no arranca nada")

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


class TestLaSuiteNoLeeTusSecretos(unittest.TestCase):
    """Las pruebas no pueden depender de lo que tengas configurado.

    Pasó de verdad: con el bot ya funcionando y un Auth Token bueno en el
    `.env`, cuatro pruebas se ponían en rojo en esa máquina y seguían verdes
    en una recién clonada. Eran justo las que comprueban «sin teléfono no
    está listo»: veían el token de verdad.

    Una suite que se comporta distinto según tu configuración no dice nada.
    Y correr las pruebas no tiene por qué cargar tus credenciales.
    """

    def test_las_credenciales_no_estan_en_el_entorno(self):
        import os

        import entorno
        for variable in entorno.CREDENCIALES:
            with self.subTest(variable=variable):
                self.assertIsNone(os.environ.get(variable))

    def test_no_se_mira_el_env_del_repo(self):
        from hugin.guardado import ajustes
        self.assertNotEqual(ajustes.fichero(), RAIZ / ".env")
        self.assertFalse(ajustes.fichero().exists())

    def test_el_env_se_busca_desde_el_directorio_de_trabajo(self):
        # Y no desde `__file__`: este módulo vive en la parte compartida, y
        # esa ruta apuntaría a la librería en vez de a la aplicación que la
        # usa. El `.env` es de quien despliega, no de quien programa.
        import os

        from hugin.guardado import ajustes
        antes = os.environ.pop(ajustes.VARIABLE, None)
        self.addCleanup(lambda: os.environ.__setitem__(ajustes.VARIABLE, antes)
                        if antes else None)
        self.assertEqual(ajustes.fichero(), Path.cwd() / ".env")

    def test_la_ruta_del_env_se_resuelve_al_llamar_no_al_definir(self):
        # La causa raíz de la primera versión de esto: la ruta estaba en un
        # argumento por defecto, y Python los evalúa UNA VEZ al definir la
        # función. Cambiar la variable después no cambiaba nada.
        from hugin.guardado import ajustes
        for funcion in (ajustes.leer, ajustes.poner,
                        ajustes.quitar, ajustes.repetidas):
            with self.subTest(funcion=funcion.__name__):
                self.assertNotIn(RAIZ / ".env", funcion.__defaults__ or ())

    def test_sin_telefono_configurado_para_la_suite(self):
        # La consecuencia que importa: da igual lo que tengas en tu .env.
        from telefono import telefonia
        self.assertIsNone(telefonia.configuracion())


class TestElCerebroEstaFuera(unittest.TestCase):
    """El corte con hugin, comprobado desde este lado.

    Partir un repo es fácil; que siga partido, no. Lo que se deshace solo es
    la dirección: alguien copia un fichero «temporalmente» para no tener que
    tocar el submódulo, y a la semana hay dos cerebros que no dicen lo mismo.
    """

    def test_hugin_esta_montado_y_declarado_como_submodulo(self):
        self.assertTrue((HUGIN / "__init__.py").exists(),
                        "hugin/ está vacío: «git submodule update --init»")
        modulos = (RAIZ / ".gitmodules").read_text(encoding="utf-8")
        self.assertIn("path = hugin", modulos)

    def test_el_cerebro_no_ha_vuelto_a_casa(self):
        # Un `mente/` aquí otra vez significa que hay dos, y el que gana es el
        # que esté antes en el sys.path, que no es una forma de decidir nada.
        for paquete in ("mente", "negocio", "guardado"):
            self.assertFalse((RAIZ / paquete).exists(),
                             f"{paquete}/ está en dos sitios: aquí y en hugin/")

    def test_al_cerebro_se_le_habla_por_su_nombre(self):
        # `from mente import fechas` funciona si alguien mete hugin/ en el
        # sys.path, y se cae en cuanto no lo mete. Se dice `hugin.mente`.
        mal = []
        for carpeta in tuple(PAQUETES) + ("tests",):
            for fichero in (RAIZ / carpeta).glob("*.py"):
                for numero, linea in enumerate(
                        fichero.read_text(encoding="utf-8").splitlines(), 1):
                    pelada = linea.strip()
                    for paquete in ("mente", "negocio", "guardado"):
                        if pelada.startswith(f"from {paquete}") \
                                or pelada == f"import {paquete}":
                            mal.append(f"{carpeta}/{fichero.name}:{numero}")
        self.assertEqual(mal, [], "eso es hugin.<paquete>")

    def test_make_pruebas_corre_tambien_las_de_hugin(self):
        # Aquí ya no queda ni una prueba de fechas, de agenda ni de reglas: si
        # «make pruebas» deja de correr las de hugin, el cerebro se queda sin
        # red y esto sigue saliendo en verde, que es lo peor que puede pasar.
        receta = (RAIZ / "Makefile").read_text(encoding="utf-8")
        trozo = receta.split("\npruebas:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("hugin", trozo, "«make pruebas» no entra en hugin/")
        self.assertIn("exit 1", trozo,
                      "si el submódulo no está, tiene que fallar, no avisar")

    def test_la_actualizacion_sola_se_trae_tambien_el_submodulo(self):
        # Un `git pull --ff-only` trae el commit con el enlace a hugin y NO
        # descarga hugin. En Madre eso es la carpeta vacía, el reinicio y el
        # teléfono mudo, sin que nada lo diga hasta que entra una llamada.
        unidad = (RAIZ / "gjallarhorn-actualizar.service.in").read_text(encoding="utf-8")
        arranque = unidad.split("ExecStart=", 1)[1]
        self.assertIn("git submodule update --init", arranque)
        self.assertLess(arranque.index("git submodule update"),
                        arranque.index("make -s reiniciar"),
                        "el submódulo se trae ANTES de reiniciar, no después")
