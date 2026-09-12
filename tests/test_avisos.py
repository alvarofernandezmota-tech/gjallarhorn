"""Pruebas de avisos.py — el rastro de lo que pasa en las llamadas.

Todo sobre temporales, y una prueba dedicada a que los avisos caigan en la
raíz de datos de gjallarhorn y en ningún otro sitio.
"""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# La raiz del repo **es** el paquete `hugin`, asi que lo que tiene que
# estar en el sys.path es la carpeta que lo contiene.
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ.parent))

import entorno  # noqa: E402,F401 — desvía los datos antes de cualquier import

from hugin.guardado import avisos  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
AYER = datetime(2026, 9, 10, 17, 30, tzinfo=MADRID)
HOY_PRONTO = datetime(2026, 9, 11, 9, 5, tzinfo=MADRID)
HOY_TARDE = datetime(2026, 9, 11, 18, 40, tzinfo=MADRID)


class CasoAvisos(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ruta = Path(self._tmp.name) / "avisos.json"

    def poblar(self):
        avisos.registrar("llamada", "Llamada de 600…123, pregunta por horarios",
                         ruta=self.ruta, ahora=AYER)
        avisos.registrar("tarifa", "Preguntó precio de revisión: 45 €",
                         ruta=self.ruta, ahora=HOY_PRONTO)
        avisos.registrar("cita", "Cita con Marta el viernes a las 10",
                         datos={"cliente": "Marta"}, ruta=self.ruta, ahora=HOY_TARDE)


class TestDondeCaen(unittest.TestCase):
    def test_los_avisos_van_a_la_raiz_de_gjallarhorn_y_a_ningun_otro_sitio(self):
        # Estos son datos de un negocio. Antes había aquí una prueba de que no
        # cayeran en un diario personal; ya no hace falta, porque gjallarhorn
        # no sabe que exista ningún otro repo.
        import os
        self.assertTrue(str(avisos.raiz()).startswith(os.environ["GJALLARHORN_DATOS"]))

    def test_la_variable_manda_sobre_la_carpeta_del_repo(self):
        # `parent.parent` porque avisos.py vive en guardado/, no en la raíz.
        # Con un solo `parent` esto comparaba contra `guardado/datos`, que no
        # existe: pasaba siempre y no comprobaba nada.
        del_repo = Path(avisos.__file__).resolve().parent.parent / "datos"
        self.assertNotEqual(avisos.raiz(), del_repo)


class TestRegistrar(CasoAvisos):
    def test_apunta_con_la_hora_de_madrid(self):
        aviso = avisos.registrar("llamada", "una llamada", ruta=self.ruta, ahora=HOY_PRONTO)
        self.assertEqual((aviso["fecha"], aviso["hora"]), ("2026-09-11", "09:05"))

    def test_los_ids_no_se_repiten_ni_se_reutilizan(self):
        ids = [avisos.registrar("llamada", f"n{i}", ruta=self.ruta)["id"] for i in range(3)]
        self.assertEqual(ids, [1, 2, 3])

    def test_un_tipo_inventado_se_rechaza_y_dice_los_que_hay(self):
        with self.assertRaises(ValueError) as caso:
            avisos.registrar("loquesea", "algo", ruta=self.ruta)
        self.assertIn("tarifa", str(caso.exception))

    def test_un_aviso_vacio_no_sirve_de_nada(self):
        with self.assertRaises(ValueError):
            avisos.registrar("llamada", "   ", ruta=self.ruta)

    def test_solo_anade_y_nunca_pisa(self):
        avisos.registrar("llamada", "la primera", ruta=self.ruta)
        avisos.registrar("cita", "la segunda", ruta=self.ruta)
        textos = [a["texto"] for a in avisos.cargar(self.ruta)]
        self.assertEqual(textos, ["la primera", "la segunda"])


class TestListarOrdenado(CasoAvisos):
    def test_lo_mas_reciente_va_primero(self):
        self.poblar()
        # Es lo que quieres ver al abrir el móvil, y por eso no es alfabético
        # ni por id: es por cuándo pasó.
        self.assertEqual([a["tipo"] for a in avisos.listar(ruta=self.ruta)],
                         ["cita", "tarifa", "llamada"])

    def test_se_puede_filtrar_por_tipo(self):
        self.poblar()
        self.assertEqual(len(avisos.listar(tipo="cita", ruta=self.ruta)), 1)

    def test_se_pueden_pedir_solo_los_nuevos(self):
        self.poblar()
        todos = avisos.listar(ruta=self.ruta)
        avisos.marcar_vistos([todos[-1]["id"]], ruta=self.ruta)
        nuevos = avisos.listar(solo_nuevos=True, ruta=self.ruta)
        self.assertEqual(len(nuevos), 2)

    def test_el_limite_recorta_por_el_final_no_por_el_principio(self):
        self.poblar()
        self.assertEqual([a["tipo"] for a in avisos.listar(limite=2, ruta=self.ruta)],
                         ["cita", "tarifa"])


class TestMarcarVistos(CasoAvisos):
    def test_sin_ids_los_marca_todos_y_dice_cuantos(self):
        self.poblar()
        self.assertEqual(avisos.marcar_vistos(ruta=self.ruta), 3)
        self.assertEqual(avisos.listar(solo_nuevos=True, ruta=self.ruta), [])

    def test_marcar_dos_veces_no_cuenta_dos_veces(self):
        self.poblar()
        avisos.marcar_vistos(ruta=self.ruta)
        self.assertEqual(avisos.marcar_vistos(ruta=self.ruta), 0)


class TestComoSeLee(CasoAvisos):
    def test_sin_avisos_lo_dice_en_vez_de_dar_un_hueco(self):
        self.assertEqual(avisos.formato([]), "Sin avisos.")

    def test_agrupa_por_dia_con_el_de_hoy_arriba(self):
        self.poblar()
        texto = avisos.formato(avisos.listar(ruta=self.ruta))
        self.assertLess(texto.index("2026-09-11"), texto.index("2026-09-10"))
        self.assertIn("📅 18:40", texto)
        self.assertIn("💶 09:05", texto)

    def test_la_cabecera_dice_cuantos_hay_y_cuantos_sin_ver(self):
        self.poblar()
        texto = avisos.formato(avisos.listar(ruta=self.ruta))
        self.assertIn("3 aviso(s)", texto)
        self.assertIn("3 sin ver", texto)

    def test_los_nuevos_se_distinguen_de_un_vistazo(self):
        self.poblar()
        lista = avisos.listar(ruta=self.ruta)
        avisos.marcar_vistos([lista[0]["id"]], ruta=self.ruta)
        texto = avisos.formato(avisos.listar(ruta=self.ruta))
        self.assertEqual(texto.count("🔵"), 2)

    def test_si_no_cabe_recorta_lo_viejo_y_LO_DICE(self):
        # Un resumen recortado en silencio hace creer que no hubo más llamadas.
        for i in range(200):
            avisos.registrar("llamada", f"llamada número {i} con un texto largo "
                             f"para llenar el mensaje", ruta=self.ruta)
        texto = avisos.formato(avisos.listar(ruta=self.ruta))
        self.assertLessEqual(len(texto), 4096, "no cabe en un mensaje de Telegram")
        self.assertIn("hay más", texto)

    def test_lo_que_cabe_entero_no_dice_que_se_ha_recortado(self):
        self.poblar()
        self.assertNotIn("hay más", avisos.formato(avisos.listar(ruta=self.ruta)))


if __name__ == "__main__":
    unittest.main()
