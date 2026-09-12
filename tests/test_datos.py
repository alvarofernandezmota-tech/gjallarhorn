"""Pruebas de que cada bot tiene lo suyo y no se mezcla con el de al lado.

Un negocio es un bot: su conocimiento, sus frases, su voz, su horario… y sus
datos. Hasta aquí los datos eran de la máquina, no del negocio, y eso se nota
en cuanto hay dos: la peluquería saludaría por su nombre a quien llamó a la
otra cosa, y los avisos de los dos saldrían mezclados en el mismo móvil.

La otra mitad de estas pruebas es la mudanza: quien ya tenía el bot
funcionando tiene sus citas y sus clientes en la carpeta de antes, y perder
eso por una mejora de organización sería el peor cambio posible.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# La raiz del repo **es** el paquete `hugin`, asi que lo que tiene que
# estar en el sys.path es la carpeta que lo contiene.
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ.parent))

import entorno  # noqa: E402

from hugin.negocio import agenda as _agenda  # noqa: E402
from hugin.guardado import almacen  # noqa: E402
from hugin.guardado import avisos  # noqa: E402
from hugin.guardado import datos  # noqa: E402
from hugin.mente import memoria  # noqa: E402
from hugin.negocio import negocio as negocios  # noqa: E402


class CasoDatos(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(entorno.aislar(self))
        datos.olvidar()
        self.addCleanup(datos.olvidar)


class TestCadaBotLoSuyo(CasoDatos):
    def test_los_avisos_de_un_negocio_no_son_los_del_otro(self):
        datos.usar("peluqueria")
        avisos.registrar("llamada", "llamada a la peluquería")
        datos.usar("taller")
        avisos.registrar("llamada", "llamada al taller")

        self.assertEqual([a["texto"] for a in avisos.listar()], ["llamada al taller"])
        datos.usar("peluqueria")
        self.assertEqual([a["texto"] for a in avisos.listar()], ["llamada a la peluquería"])

    def test_los_clientes_tampoco(self):
        datos.usar("peluqueria")
        memoria.apuntar_llamada("+34600111222", "Marta")
        datos.usar("taller")
        self.assertIsNone(memoria.ficha("+34600111222"),
                          "un cliente de la peluquería no es cliente del taller")
        datos.usar("peluqueria")
        self.assertEqual(memoria.ficha("+34600111222").nombre, "Marta")

    def test_la_agenda_va_en_la_misma_carpeta_que_lo_demas(self):
        datos.usar("peluqueria")
        self.assertEqual(_agenda._ruta("peluqueria").parent, datos.carpeta())
        self.assertEqual(_agenda._ruta("peluqueria").name, "agenda.json")

    def test_la_agenda_de_otro_negocio_no_hace_falta_fijar_nada(self):
        # La agenda siempre sabe de qué negocio es: se le pasa por el nombre.
        datos.usar("peluqueria")
        self.assertEqual(_agenda._ruta("taller").parent.name, "taller")

    def test_todo_lo_de_un_bot_cuelga_de_su_carpeta(self):
        datos.usar("peluqueria")
        avisos.registrar("llamada", "algo")
        memoria.apuntar_llamada("+34600111222", "Marta")
        _agenda.Agenda("peluqueria", None).reservar("2030-01-01", "10:00", 30, None, "Marta")
        suyos = sorted(p.name for p in (self.raiz / "peluqueria").iterdir())
        self.assertEqual(suyos, ["agenda.json", "avisos.json", "clientes.json"])

    def test_sin_fijar_nada_se_queda_donde_siempre(self):
        # Una prueba que no fija negocio, o una orden suelta, sigue viendo la
        # carpeta de datos a secas. Nada se rompe por no llamar a `usar`.
        self.assertIsNone(datos.cual())
        self.assertEqual(datos.carpeta(), datos.raiz())
        avisos.registrar("llamada", "sin negocio")
        self.assertTrue((self.raiz / "avisos.json").exists())


class TestSeAceptaElNegocioEntero(CasoDatos):
    def test_vale_el_nombre_o_el_negocio(self):
        negocio = negocios.cargar("peluqueria")
        datos.usar(negocio)
        self.assertEqual(datos.cual(), "peluqueria")
        datos.usar("taller")
        self.assertEqual(datos.cual(), "taller")


class TestLaMudanza(CasoDatos):
    """Lo que ya estaba escrito con el reparto viejo no se pierde."""

    def escribir_lo_viejo(self):
        almacen.guardar(self.raiz / "avisos.json",
                        [{"id": 1, "tipo": "llamada", "texto": "de antes",
                          "fecha": "2026-09-01", "hora": "10:00"}], avisos.VERSION)
        almacen.guardar(self.raiz / "clientes.json",
                        {"+34600111222": {"nombre": "Marta", "llamadas": 3}},
                        memoria.ESQUEMA)
        (self.raiz / "agenda").mkdir(parents=True, exist_ok=True)
        almacen.guardar(self.raiz / "agenda" / "peluqueria.json",
                        [{"id": 1, "fecha": "2030-01-01", "hora": "10:00", "duracion": 30,
                          "servicio": "Tinte", "nombre": "Marta", "creada": "2026-09-01 10:00"}],
                        _agenda.ESQUEMA)

    def test_los_ficheros_viejos_se_mudan_solos(self):
        self.escribir_lo_viejo()
        movidos = datos.usar("peluqueria")
        self.assertEqual(sorted(movidos),
                         ["agenda/peluqueria.json", "avisos.json", "clientes.json"])
        self.assertEqual(avisos.listar()[0]["texto"], "de antes")
        self.assertEqual(memoria.ficha("+34600111222").nombre, "Marta")
        self.assertEqual(_agenda.Agenda("peluqueria", None).citas()[0]["servicio"], "Tinte")

    def test_la_mudanza_no_deja_nada_atras(self):
        self.escribir_lo_viejo()
        datos.usar("peluqueria")
        self.assertFalse((self.raiz / "avisos.json").exists())
        self.assertFalse((self.raiz / "clientes.json").exists())

    def test_se_hace_una_vez_y_no_se_repite(self):
        self.escribir_lo_viejo()
        self.assertTrue(datos.usar("peluqueria"))
        self.assertEqual(datos.usar("peluqueria"), [], "ya estaba mudado")

    def test_si_ya_hay_datos_nuevos_no_se_pisa_nada(self):
        # Dos ficheros con datos no se fusionan a ciegas: se queda el nuevo y
        # el viejo se deja donde está para que alguien lo mire.
        self.escribir_lo_viejo()
        datos.usar("peluqueria")
        avisos.registrar("llamada", "de ahora")
        datos.olvidar()
        almacen.guardar(self.raiz / "avisos.json",
                        [{"id": 9, "tipo": "llamada", "texto": "otro viejo",
                          "fecha": "2026-09-02", "hora": "10:00"}], avisos.VERSION)
        self.assertEqual(datos.usar("peluqueria"), [])
        self.assertTrue((self.raiz / "avisos.json").exists())
        textos = [a["texto"] for a in avisos.listar()]
        self.assertIn("de ahora", textos)
        self.assertNotIn("otro viejo", textos)

    def test_sin_nada_viejo_no_hace_nada(self):
        self.assertEqual(datos.usar("peluqueria"), [])


class TestLaCarpetaSeMueve(unittest.TestCase):
    def test_la_variable_manda(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        import os
        antes = os.environ.get(datos.VARIABLE)
        os.environ[datos.VARIABLE] = tmp.name
        datos.olvidar()
        self.addCleanup(datos.olvidar)
        self.addCleanup(lambda: os.environ.__setitem__(datos.VARIABLE, antes)
                        if antes else os.environ.pop(datos.VARIABLE, None))
        datos.usar("peluqueria")
        self.assertEqual(datos.carpeta(), Path(tmp.name) / "peluqueria")
        avisos.registrar("llamada", "ahí dentro")
        guardado = json.loads((Path(tmp.name) / "peluqueria" / "avisos.json").read_text())
        self.assertEqual(guardado["datos"][0]["texto"], "ahí dentro")

class TestCadaBotHablaASuManera(unittest.TestCase):
    """El mismo código atiende dos negocios que no hablan igual.

    Es lo que quiere decir «cada bot con su personalidad»: la peluquería
    trata de usted y el taller tutea, y no hay una línea de Python que sepa
    eso. Está en `negocio.toml` y en `frases.toml`.

    El taller de estas pruebas es **de las pruebas** —igual que la
    peluquería—, aunque el repo traiga otro igual como ejemplo: así, editar
    el ejemplo no rompe la suite.
    """

    def setUp(self):
        entorno.aislar(self)
        datos.olvidar()
        self.addCleanup(datos.olvidar)
        from hugin.negocio import frases
        frases.olvidar()
        self.addCleanup(frases.olvidar)

    def atender(self, negocio, *frases_):
        from hugin.mente import recepcion
        datos.usar(negocio)
        n = negocios.cargar(negocio)
        llamada = recepcion.conversacion_de(n)
        return [llamada.atender(f).texto for f in frases_], n

    def test_uno_trata_de_usted_y_el_otro_tutea(self):
        guion = ("quiero cita de tinte el jueves a las cinco de la tarde", "me llamo Marta")
        dichos, peluqueria = self.atender("peluqueria", *guion)
        dicho = " ".join(dichos)
        self.assertIn("se la apunto", dicho)
        self.assertNotIn("te la apunto", dicho)
        self.assertIn("asistente automático", peluqueria.saludo)

        dichos, _ = self.atender("taller", "quiero cita el jueves a las diez", "soy Álvaro")
        dicho = " ".join(dichos)
        self.assertIn("te la apunto", dicho)
        self.assertNotIn("se la apunto", dicho)

    def test_cada_uno_con_su_voz_y_su_saludo(self):
        self.assertEqual(negocios.cargar("taller").voz, "Polly.Sergio")
        self.assertIsNone(negocios.cargar("peluqueria").voz)
        self.assertIn("Taller Ruiz", negocios.cargar("taller").saludo)

    def test_cada_uno_con_sus_servicios_y_sus_sinonimos(self):
        dichos, _ = self.atender("taller", "¿cuánto cuesta cambiar las ruedas?")
        self.assertIn("180", dichos[0])
        # Y lo del taller no existe en la peluquería, ni al revés.
        dichos, _ = self.atender("peluqueria", "¿cuánto cuesta cambiar las ruedas?")
        self.assertIn("No tengo ese servicio", dichos[0])

    def test_y_cada_uno_con_su_horario(self):
        self.assertTrue(negocios.cargar("taller").horario.abre(__import__("datetime").date(2026, 9, 14)))
        self.assertFalse(negocios.cargar("peluqueria").horario.abre(__import__("datetime").date(2026, 9, 14)))


if __name__ == "__main__":
    unittest.main()
