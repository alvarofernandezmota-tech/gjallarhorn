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

# Lo que es de gjallarhorn: por dónde entra la conversación y quién la opera.
# El cerebro —`mente`, `negocio`, `guardado`— ya no está aquí: vive en hugin,
# montado como submódulo ([ADR-019]). Esa es la frontera que vigila
# `TestLaFronteraConHugin`, más abajo.
PAQUETES = {"telefono", "dueno"}

# Los del cerebro, que tienen que estar DENTRO de hugin y no fuera.
DE_HUGIN = ("mente", "negocio", "guardado")


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
            # Puede tener dos partes (`dueno.panel`) o tres, ahora que el
            # cerebro va por el submódulo (`hugin.mente.cerebro`).
            ruta = RAIZ.joinpath(*orden.split(".")).with_suffix(".py")
            with self.subTest(orden=orden):
                self.assertTrue(ruta.exists(), f"«make» llama a {orden} y no está")

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

    def test_la_actualizacion_sola_trae_el_submodulo_antes_de_reiniciar(self):
        # El ADR-019 lo promete con estas palabras: "la unidad trae el
        # submódulo antes de reiniciar, y si no puede, no reinicia". Sin
        # esto, `git pull --ff-only` en el servicio de Madre mueve el
        # puntero de `.gitmodules` pero no descarga hugin/, y el `make
        # reiniciar` de detrás tira el proceso que SÍ tenía el cerebro
        # cargado por uno que revienta con ImportError en el primer
        # mensaje: el bot se queda mudo sin que nada lo diga.
        texto = (RAIZ / "gjallarhorn-actualizar.service.in").read_text(encoding="utf-8")
        self.assertIn("git submodule update", texto)
        # Y en el orden que importa: si el pull trae commits nuevos pero el
        # submódulo no se puede traer, `reiniciar` no debe llegar a correr.
        antes_de_reiniciar = texto.split("make -s reiniciar")[0]
        self.assertIn("git submodule update", antes_de_reiniciar)


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
        from dueno import avisar
        self.assertNotEqual(avisar.FICHERO_ENV, RAIZ / ".env")
        self.assertFalse(avisar.FICHERO_ENV.exists())

    def test_pero_la_raiz_sigue_siendo_la_de_verdad(self):
        # Apartar el .env no puede mover la raíz: de ella cuelgan negocios/,
        # datos/ y la plantilla del servicio.
        from dueno import avisar
        self.assertEqual(avisar.RAIZ, RAIZ)

    def test_la_ruta_del_env_se_resuelve_al_llamar_no_al_definir(self):
        # La causa raíz. Estaba en un argumento por defecto, y Python los
        # evalúa UNA VEZ al definir la función: cambiar la variable después
        # no cambiaba nada, y las pruebas no podían apartarse.
        from dueno import avisar
        for funcion in (avisar._leer_env, avisar.poner_en_env,
                        avisar.quitar_del_env, avisar.repetidas_en_env):
            with self.subTest(funcion=funcion.__name__):
                self.assertNotIn(RAIZ / ".env", funcion.__defaults__ or ())

    def test_sin_telefono_configurado_para_la_suite(self):
        # La consecuencia que importa: da igual lo que tengas en tu .env.
        from telefono import telefonia
        self.assertIsNone(telefonia.configuracion())


class TestLaFronteraConHugin(unittest.TestCase):
    """La mitad de la frontera del [ADR-019] que le toca a gjallarhorn.

    La otra mitad está en hugin (`tests/test_libreria.py`), que se cae si el
    cerebro importa un canal. Se comprueba desde los dos lados a propósito:
    una frontera que solo se mira desde uno se cruza por el otro.
    """

    def modulos(self):
        for carpeta in (*PAQUETES, "tests"):
            yield from sorted((RAIZ / carpeta).rglob("*.py"))

    def test_el_cerebro_no_ha_vuelto_a_casa(self):
        # Copiar `mente/` aquí «para probar una cosa» y olvidarlo dentro es
        # la forma fácil de acabar con dos cerebros que se van separando.
        for carpeta in DE_HUGIN:
            with self.subTest(carpeta=carpeta):
                self.assertFalse((RAIZ / carpeta).exists(),
                                 f"{carpeta}/ tiene que vivir en hugin, no aquí")

    def test_al_cerebro_se_le_habla_por_su_nombre(self):
        # `from mente import x` funcionaría si alguien deja una copia suelta,
        # y entonces no se sabe cuál de los dos se está usando.
        mal = []
        for fichero in self.modulos():
            for numero, linea in enumerate(
                    fichero.read_text(encoding="utf-8").splitlines(), 1):
                if re.match(rf"\s*(from|import)\s+({'|'.join(DE_HUGIN)})\b", linea):
                    mal.append(f"{fichero.relative_to(RAIZ)}:{numero}: {linea.strip()}")
        self.assertEqual(mal, [], "\n".join([
            "se le habla al cerebro sin decir de dónde sale:", *mal,
            "", "Es `from hugin.mente import ...`, no `from mente import ...`.",
        ]))

    def test_el_submodulo_esta_declarado_y_traido(self):
        self.assertIn("path = hugin",
                      (RAIZ / ".gitmodules").read_text(encoding="utf-8"))
        # Un submódulo sin inicializar es una carpeta vacía, y el fallo sale
        # luego como un ImportError que no dice que falte un `git submodule`.
        self.assertTrue((RAIZ / "hugin" / "mente" / "recepcion.py").exists(),
                        "hugin está vacío: falta `git submodule update --init`")

    def test_make_pruebas_entra_en_el_submodulo(self):
        # Sin esto, `make pruebas` sale en verde con hugin roto.
        texto = (RAIZ / "Makefile").read_text(encoding="utf-8")
        objetivo = texto.split("\npruebas:")[1].split("\n\n")[0]
        self.assertIn("cd hugin", objetivo,
                      "«make pruebas» no corre las pruebas de hugin")
