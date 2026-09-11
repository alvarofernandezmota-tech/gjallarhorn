"""Pruebas de las copias: lo peor que puede pasar aquí es perder las citas.

Y la segunda peor es restaurar la copia equivocada y quedarse sin las dos
versiones. Por eso la mitad de estas pruebas son de eso: que restaurar
guarde antes lo que había.
"""

import json
import sys
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

from negocio import agenda as _agenda  # noqa: E402
from dueno import agentes  # noqa: E402
from guardado import avisos  # noqa: E402
from guardado import copias  # noqa: E402
from guardado import datos  # noqa: E402
from mente import memoria  # noqa: E402
from negocio import negocio as negocios  # noqa: E402

HOY = date(2026, 9, 11)


class CasoCopias(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(entorno.aislar(self))
        datos.olvidar()
        self.addCleanup(datos.olvidar)
        datos.usar("peluqueria")

    def con_datos(self):
        avisos.registrar("llamada", "una llamada")
        memoria.apuntar_llamada("+34600111222", "Marta")
        _agenda.Agenda("peluqueria", None).reservar("2030-01-01", "10:00", 30, "Tinte", "Marta")


class TestHacerLaCopia(CasoCopias):
    def test_copia_lo_que_no_se_puede_perder(self):
        self.con_datos()
        destino, copiados = copias.hacer(hoy=HOY)
        self.assertEqual(sorted(copiados), ["agenda.json", "avisos.json", "clientes.json"])
        self.assertEqual(destino.name, "2026-09-11")
        guardada = json.loads((destino / "agenda.json").read_text())
        self.assertEqual(guardada["datos"][0]["servicio"], "Tinte")

    def test_sin_datos_no_inventa_ficheros(self):
        _, copiados = copias.hacer(hoy=HOY)
        self.assertEqual(copiados, [])

    def test_repetirla_el_mismo_dia_la_sobrescribe(self):
        self.con_datos()
        copias.hacer(hoy=HOY)
        avisos.registrar("llamada", "otra más")
        destino, _ = copias.hacer(hoy=HOY)
        self.assertEqual(copias.listar(), ["2026-09-11"])
        guardados = json.loads((destino / "avisos.json").read_text())["datos"]
        self.assertEqual(len(guardados), 2, "la copia es cómo estaba hoy, no un histórico")

    def test_las_copias_van_dentro_del_negocio(self):
        self.con_datos()
        destino, _ = copias.hacer(hoy=HOY)
        self.assertEqual(destino.parent.parent, self.raiz / "peluqueria")

    def test_cada_negocio_las_suyas(self):
        self.con_datos()
        copias.hacer(hoy=HOY)
        datos.usar("taller")
        self.assertEqual(copias.listar(), [])
        datos.usar("peluqueria")
        self.assertEqual(copias.listar(), ["2026-09-11"])


class TestLimpiarLasViejas(CasoCopias):
    def test_se_guardan_las_ultimas(self):
        self.con_datos()
        for dia in range(1, 21):
            copias.hacer(hoy=date(2026, 9, dia))
        borradas = copias.limpiar(cuantas=14)
        self.assertEqual(len(borradas), 6)
        self.assertEqual(len(copias.listar()), 14)
        self.assertEqual(copias.listar()[-1], "2026-09-20", "la última es la más nueva")

    def test_con_pocas_no_borra_nada(self):
        self.con_datos()
        copias.hacer(hoy=HOY)
        self.assertEqual(copias.limpiar(cuantas=14), [])


class TestRestaurar(CasoCopias):
    def test_pone_la_copia_de_ese_dia(self):
        self.con_datos()
        copias.hacer(hoy=HOY)
        _agenda.Agenda("peluqueria", None).anular(1)
        self.assertEqual(_agenda.Agenda("peluqueria", None).citas(), [])

        puestos = copias.restaurar("2026-09-11", hoy=HOY)
        self.assertIn("agenda.json", puestos)
        self.assertEqual(_agenda.Agenda("peluqueria", None).citas()[0]["servicio"], "Tinte")

    def test_guarda_lo_que_habia_antes_de_pisarlo(self):
        self.con_datos()
        copias.hacer(hoy=HOY)
        avisos.registrar("llamada", "lo de después de la copia")
        copias.restaurar("2026-09-11", hoy=HOY)

        # Lo de después de la copia ya no está en los datos…
        self.assertNotIn("lo de después de la copia",
                         [a["texto"] for a in avisos.listar()])
        # …pero no se ha perdido.
        guardado = copias.carpeta() / "antes-de-restaurar-2026-09-11" / "avisos.json"
        textos = [a["texto"] for a in json.loads(guardado.read_text())["datos"]]
        self.assertIn("lo de después de la copia", textos)

    def test_una_copia_que_no_existe_no_borra_nada(self):
        self.con_datos()
        with self.assertRaises(FileNotFoundError):
            copias.restaurar("2020-01-01", hoy=HOY)
        self.assertEqual(len(_agenda.Agenda("peluqueria", None).citas()), 1)


class TestElAgente(CasoCopias):
    def test_hace_la_copia_y_no_dice_nada(self):
        self.con_datos()
        negocio = negocios.cargar("peluqueria")
        mundo = agentes.mundo_de(negocio)
        self.assertIsNone(agentes.copia(mundo), "una copia que sale bien no es noticia")
        self.assertTrue(copias.listar())

    def test_si_no_puede_copiar_lo_dice(self):
        self.con_datos()
        negocio = negocios.cargar("peluqueria")
        mundo = agentes.mundo_de(negocio)

        def revienta(*_, **__):
            raise OSError(28, "No space left on device")

        antes = copias.hacer
        copias.hacer = revienta
        self.addCleanup(lambda: setattr(copias, "hacer", antes))
        resultado = agentes.copia(mundo)
        self.assertIsNotNone(resultado)
        self.assertIn("No he podido copiar", resultado.titulo)
        self.assertEqual(resultado.tipo, "fallo")

    def test_esta_dado_de_alta_en_la_colmena(self):
        self.assertIn("copia", agentes.TODOS)


class TestLaOrden(CasoCopias):
    def correr(self, *argumentos):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = copias.main(list(argumentos))
        return codigo, salida.getvalue()

    def test_hacer_y_listar(self):
        self.con_datos()
        codigo, dicho = self.correr()
        self.assertEqual(codigo, 0)
        self.assertIn("copia en", dicho)
        codigo, dicho = self.correr("--listar")
        self.assertIn("3 fichero(s)", dicho)

    def test_restaurar_una_que_no_hay_avisa_y_no_revienta(self):
        self.con_datos()
        codigo, dicho = self.correr("--restaurar", "2020-01-01")
        self.assertEqual(codigo, 1)
        self.assertIn("no hay copia", dicho)

    def test_sin_datos_lo_dice(self):
        codigo, dicho = self.correr()
        self.assertEqual(codigo, 0)
        self.assertIn("nada que copiar", dicho)


if __name__ == "__main__":
    unittest.main()
