"""Pruebas de acciones.py, la capa 1 del ADR-018.

Contra los módulos **reales** de midgaror, no contra dobles: lo que se quiere
comprobar es justamente que envolver esas funciones sale bien, y un doble
comprobaría que el doble funciona. Lo que sí es de mentira son las rutas: todo
va a un directorio temporal.

**Nada de esto toca `diario/personal/` ni los JSON de verdad.** Hay una prueba
dedicada a que eso siga siendo cierto, porque es el error que no se puede
cometer ni una vez: el bot escribe ahí en producción.
"""

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# gjallarhorn se desarrolla fuera del árbol de midgaror, así que la posición de
# submódulo no vale y hay que decir dónde está. Antes del primer import: el
# sys.path de midgaror.py se monta al importarlo.
import entorno  # noqa: E402,F401 — fija MIDGAROR_DATOS antes de cualquier import

import acciones  # noqa: E402
import midgaror  # noqa: E402

diario = midgaror.modulo("diario")
organizar = midgaror.modulo("organizar_diario")

HOY = "2026-09-11"


class CasoAcciones(unittest.TestCase):
    """Cada prueba con su temporal, y el diario real fuera de alcance."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

        # `escribir_entrada` no lleva parámetro de ruta: el destino sale de
        # estas dos constantes. Se redirigen las dos porque ruta_de_hoy vive en
        # diario.py y ruta_de_fecha en organizar_diario.py.
        for mod in (diario, organizar):
            anterior = mod.CARPETA_PERSONAL
            mod.CARPETA_PERSONAL = self.base / "personal"
            self.addCleanup(setattr, mod, "CARPETA_PERSONAL", anterior)

    def rutas(self) -> dict:
        return {m: self.base / f"{m}.json" for m in ("tareas", "agenda", "habitos")}


class TestElAislamientoSigueEnSuSitio(unittest.TestCase):
    """Sin esto, un olvido vuelve a escribir en los datos de Alvaro."""

    def test_la_raiz_de_datos_es_un_temporal(self):
        ubicacion = midgaror.modulo("ubicacion")
        self.assertEqual(ubicacion.raiz(), entorno.DATOS.resolve(),
                         "MIDGAROR_DATOS no apunta al temporal de las pruebas")

    def test_los_json_por_defecto_caen_fuera_de_midgaror(self):
        # La comprobacion directa: donde escribiria una accion que se olvide
        # de pasar `ruta`.
        for modelo in ("tareas", "agenda", "habitos", "registro"):
            ruta = midgaror.modulo("ubicacion").json_modelo(modelo)
            self.assertFalse(
                str(ruta).startswith(str(midgaror.MIDGAROR)),
                f"{modelo}: por defecto escribiria en midgaror de verdad ({ruta})")


class TestElDiarioRealNoSeToca(CasoAcciones):
    def test_las_constantes_apuntan_al_temporal(self):
        # Si esta prueba falla, las demás están escribiendo en el diario de
        # Álvaro. Es la primera por eso.
        for mod in (diario, organizar):
            self.assertTrue(
                str(mod.CARPETA_PERSONAL).startswith(str(self.base)),
                f"{mod.__name__}.CARPETA_PERSONAL apunta fuera del temporal")

    def test_apuntar_escribe_dentro_del_temporal_y_en_ningun_otro_sitio(self):
        acciones.ejecutar("apuntar_en_diario", texto="probando", fecha=HOY)
        escritos = list((self.base / "personal").rglob("*.md"))
        self.assertEqual([p.name for p in escritos], [f"{HOY}.md"])


class TestAcciones(CasoAcciones):
    def test_apuntar_en_el_diario_deja_el_texto_en_la_entrada(self):
        respuesta = acciones.ejecutar("apuntar_en_diario", texto="he ido a correr", fecha=HOY)
        entrada = (self.base / "personal" / "2026" / "09-septiembre" / f"{HOY}.md")
        self.assertIn("he ido a correr", entrada.read_text(encoding="utf-8"))
        self.assertIn("Apuntado", respuesta)

    def test_crear_tarea_saca_la_fecha_del_texto(self):
        ruta = self.base / "tareas.json"
        respuesta = acciones.crear_tarea("llamar al dentista mañana", ruta=ruta)
        guardadas = acciones.tareas.cargar(ruta)
        self.assertEqual(len(guardadas), 1)
        self.assertTrue(guardadas[0]["fecha"], "no guardó el «mañana» como fecha")
        self.assertIn("dentista", respuesta)

    def test_crear_cita_avisa_del_solape(self):
        ruta = self.base / "agenda.json"
        acciones.crear_cita("dentista mañana a las 10", ruta=ruta)
        respuesta = acciones.crear_cita("fisio mañana a las 10", ruta=ruta)
        self.assertIn("solapa", respuesta)

    def test_marcar_habito_sin_valor_es_si_o_no(self):
        ruta = self.base / "habitos.json"
        respuesta = acciones.marcar_habito("Gimnasio", fecha=HOY, ruta=ruta)
        # La frase entera, no «sale la palabra»: antes decia
        # «2026-09-11 el gimnasio: ✅» —la fecha y el nombre cambiados— y esta
        # prueba pasaba igual, porque las dos cosas salian.
        self.assertEqual(respuesta, f"gimnasio el {HOY}: ✅.")

    def test_marcar_habito_con_valor_guarda_el_numero(self):
        ruta = self.base / "habitos.json"
        respuesta = acciones.marcar_habito("animo", valor=7, fecha=HOY, ruta=ruta)
        self.assertEqual(respuesta, f"animo el {HOY}: 7.")

    def test_apuntar_en_el_registro_dice_cuanto(self):
        ruta = self.base / "registro.json"
        respuesta = acciones.apuntar_registro("lectura", valor=1.5, unidad="h", ruta=ruta)
        self.assertIn("lectura", respuesta)
        self.assertIn("1.5", respuesta)

    def test_leer_un_dia_sin_entrada_lo_dice_y_no_escribe(self):
        respuesta = acciones.ejecutar("leer_diario", fecha="2019-03-07")
        self.assertIn("Sin entrada", respuesta)
        self.assertFalse((self.base / "personal").exists(),
                         "leer ha creado carpetas: leer nunca escribe")

    def test_que_hay_hoy_junta_los_tres_modelos(self):
        rutas = self.rutas()
        acciones.crear_tarea("comprar el pan hoy", ruta=rutas["tareas"])
        acciones.crear_cita("dentista hoy a las 10", ruta=rutas["agenda"])
        respuesta = acciones.que_hay_hoy(rutas=rutas)
        self.assertIn("pan", respuesta)
        self.assertIn("dentista", respuesta)


class TestElCatalogo(unittest.TestCase):
    def test_hay_una_accion_por_cada_cosa_que_sabe_hacer_el_diario(self):
        self.assertEqual(
            sorted(acciones.ACCIONES),
            ["apuntar_en_diario", "apuntar_registro", "crear_cita", "crear_tarea",
             "leer_diario", "marcar_habito", "que_hay_hoy"])

    def test_el_esquema_tiene_la_forma_que_esperan_los_llm(self):
        for herramienta in acciones.catalogo():
            self.assertEqual(herramienta["type"], "function")
            funcion = herramienta["function"]
            self.assertTrue(funcion["name"])
            self.assertTrue(funcion["description"], f"{funcion['name']} sin descripción")
            self.assertEqual(funcion["parameters"]["type"], "object")

    def test_los_obligatorios_estan_entre_las_propiedades(self):
        for accion in acciones.ACCIONES.values():
            for obligatorio in accion.obligatorios:
                self.assertIn(obligatorio, accion.propiedades,
                              f"{accion.nombre}: exige {obligatorio} y no lo describe")

    def test_ninguna_accion_le_ensena_al_modelo_donde_se_escribe(self):
        # `ruta` y `rutas` son para las pruebas. Si se colaran en el esquema, el
        # modelo podría elegir en qué fichero escribe.
        for accion in acciones.ACCIONES.values():
            self.assertNotIn("ruta", accion.propiedades, accion.nombre)
            self.assertNotIn("rutas", accion.propiedades, accion.nombre)


class TestEjecutar(CasoAcciones):
    def test_una_accion_que_no_existe_lo_dice_y_lista_las_que_hay(self):
        with self.assertRaises(ValueError) as caso:
            acciones.ejecutar("borrar_el_diario")
        self.assertIn("crear_tarea", str(caso.exception))

    def test_un_argumento_inventado_se_descarta_en_vez_de_reventar(self):
        # Un modelo se inventa parámetros. Que eso rompa el agente sería peor.
        acciones.ejecutar("apuntar_en_diario", texto="hola", fecha=HOY, humor="alegre")
        entrada = self.base / "personal" / "2026" / "09-septiembre" / f"{HOY}.md"
        self.assertTrue(entrada.exists())

    def test_no_se_puede_colar_la_ruta_desde_fuera(self):
        # La prueba que de verdad importa: aunque el modelo mande `ruta`, la
        # escritura va a donde manda midgaror, no a donde diga él.
        otra = self.base / "elegida-por-el-modelo.md"
        acciones.ejecutar("apuntar_en_diario", texto="hola", fecha=HOY, ruta=str(otra))
        self.assertFalse(otra.exists())

    def test_toda_accion_se_puede_llamar_con_sus_propios_nombres(self):
        """El fallo que las pruebas no vieron y sí vio ejecutarlo.

        `ejecutar` recibia el nombre de la accion en un parametro llamado
        `nombre`, y `marcar_habito` tiene un argumento que tambien se llama
        `nombre`: «got multiple values for argument 'nombre'».

        Se comprueba **atando la firma, sin ejecutar nada**. La primera version
        de esta prueba SI ejecutaba, sin pasar `ruta`, y escribio cuatro tareas
        «algo» y cuatro cafes en el tareas.json y el registro.json de verdad de
        Alvaro --commiteados incluidos--. Para comprobar que la llamada encaja
        no hace falta llamar.
        """
        import inspect
        muestras = {"texto": "algo", "nombre": "gimnasio", "que": "cafe",
                    "fecha": HOY, "valor": 1, "unidad": "h"}
        firma = inspect.signature(acciones.ejecutar)
        for accion in acciones.ACCIONES.values():
            argumentos = {p: muestras[p] for p in accion.propiedades if p in muestras}
            with self.subTest(accion=accion.nombre):
                try:
                    firma.bind(accion.nombre, **argumentos)
                except TypeError as error:
                    self.fail(f"{accion.nombre} choca con ejecutar(): {error}")

    def test_sin_lo_obligatorio_avisa_de_que_falta(self):
        with self.assertRaises(ValueError) as caso:
            acciones.ejecutar("crear_tarea")
        self.assertIn("texto", str(caso.exception))


if __name__ == "__main__":
    unittest.main()
