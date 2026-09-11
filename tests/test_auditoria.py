"""Los defectos que encontró la auditoría, cada uno con su prueba.

La auditoría se quedó a medias —los verificadores murieron por límite de
sesión— así que estos seis se comprobaron **a mano, leyendo y ejecutando**,
antes de arreglarlos. Lo que hay aquí es lo que impide que vuelvan.
"""

import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

from negocio import agenda as ag  # noqa: E402
from dueno import avisar  # noqa: E402
from guardado import avisos  # noqa: E402
from dueno import diagnostico  # noqa: E402
from negocio import negocio as negocios  # noqa: E402
from telefono import servidor  # noqa: E402
from telefono import telefonia  # noqa: E402


class TestElCuerpoDeLaPeticion(unittest.TestCase):
    """Un `Content-Length` mentido entra por un puerto público."""

    def handler(self, content_length, cuerpo=b""):
        h = servidor.Comun.__new__(servidor.Recepcion)
        h.headers = {"Content-Length": content_length}
        h.rfile = io.BytesIO(cuerpo)
        return h

    def test_un_largo_negativo_no_lee_hasta_el_fin_del_mundo(self):
        # `min(-1, tope)` es -1 y `read(-1)` lee hasta EOF. En un servidor
        # así, una conexión que no cierra deja el teléfono mudo.
        self.assertIsNone(self.handler("-1", b"x" * 100)._cuerpo(1000))

    def test_un_largo_que_no_es_un_numero_tampoco_revienta(self):
        self.assertIsNone(self.handler("abc")._cuerpo(1000))

    def test_sin_cabecera_es_un_cuerpo_vacio(self):
        h = servidor.Comun.__new__(servidor.Recepcion)
        h.headers = {}
        h.rfile = io.BytesIO(b"")
        self.assertEqual(h._cuerpo(1000), b"")

    def test_nunca_lee_mas_del_tope_aunque_lo_pidan(self):
        self.assertEqual(len(self.handler("999999", b"x" * 5000)._cuerpo(100)), 100)

    def test_el_webhook_usa_el_tope_de_un_formulario_no_el_del_audio(self):
        # Aceptar 10 MB en el webhook era usar el tope del audio para algo
        # que son unos cientos de bytes.
        self.assertLess(servidor.TOPE_FORMULARIO, servidor.TOPE_AUDIO)


class TestNoSeQuedaColgado(unittest.TestCase):
    def test_hay_un_tope_de_espera_en_las_conexiones(self):
        # Sin esto, una conexión que abre y no manda nada se queda ahí.
        self.assertIsNotNone(servidor.Comun.timeout)
        self.assertGreater(servidor.Comun.timeout, 0)

    def test_el_servidor_atiende_varias_a_la_vez(self):
        # El docstring de telefonia.py dice «pueden entrar dos a la vez». Con
        # un servidor de un hilo eso era falso: se servían en serie.
        from http.server import ThreadingHTTPServer
        self.assertIs(servidor.ThreadingHTTPServer, ThreadingHTTPServer)


class TestDondeEscucha(unittest.TestCase):
    def test_por_defecto_solo_localhost(self):
        # Tailscale proxya desde localhost, así que 0.0.0.0 no hacía falta y
        # dejaba la demo al alcance de toda la red de casa.
        servidor_ = servidor._abrir(0, servidor.Recepcion, "prueba", "--puerto")
        self.addCleanup(servidor_.server_close)
        self.assertEqual(servidor_.server_address[0], "127.0.0.1")

    def test_con_lan_se_abre_a_la_red(self):
        servidor_ = servidor._abrir(0, servidor.Recepcion, "prueba", "--puerto", lan=True)
        self.addCleanup(servidor_.server_close)
        self.assertEqual(servidor_.server_address[0], "0.0.0.0")


class TestElInformeNoLlevaDatosDeNadie(unittest.TestCase):
    """`make diagnostico` está hecho para pegarse en un chat."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        entorno.aislar(self)
        self.negocio = negocios.cargar("peluqueria")
        agenda = ag.Agenda("peluqueria", self.negocio.horario,
                           ruta=Path(self._tmp.name) / "agenda.json")
        agenda.reservar("2026-12-24", "10:00", 30, "Corte de caballero", "Consuelo Ramírez")
        avisos.registrar("llamada", "Llamada de +34611223344 (Consuelo Ramírez)")

    def informe(self):
        return diagnostico.informe("peluqueria", 1, corto=False)

    def test_no_sale_el_nombre_de_un_cliente(self):
        self.assertNotIn("Consuelo", self.informe())

    def test_no_sale_un_telefono(self):
        self.assertNotRegex(self.informe(), r"\+?\d{9,}")

    def test_no_sale_la_ruta_de_los_datos(self):
        import os
        os.environ["GJALLARHORN_DATOS"] = "/home/unapersona/sus/datos"
        self.assertNotIn("unapersona", self.informe())

    def test_pero_sigue_diciendo_cuantas_cosas_hay(self):
        texto = self.informe()
        self.assertIn("avisos:", texto)
        self.assertIn("citas:", texto)


class TestNoSePierdeNingunAviso(unittest.TestCase):
    """Lo peor que encontró la auditoría: avisos dados por enviados sin enviar."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ruta = Path(self._tmp.name) / "avisos.json"
        for i in range(400):
            avisos.registrar("cita", f"Cita {i} " + "x" * 70, ruta=self.ruta)

    def test_encajar_siempre_mete_al_menos_uno(self):
        # Si no, un aviso larguísimo bloquea la cola detrás de él para siempre.
        largo = [{"id": 1, "tipo": "cita", "texto": "x" * 9000,
                  "fecha": "2026-09-11", "hora": "10:00", "visto": False}]
        self.assertEqual(len(avisos.encajar(largo, tope=100)), 1)

    def test_el_formato_recorta_por_avisos_no_por_dias_enteros(self):
        # Antes se descartaba el bloque del día entero: con 400 avisos del
        # mismo día no cabía NINGUNO y el mensaje salía vacío.
        texto = avisos.formato(avisos.listar(ruta=self.ruta))
        self.assertGreater(sum(1 for linea in texto.splitlines() if "Cita " in linea), 0)
        self.assertLessEqual(len(texto), avisos.TOPE_TELEGRAM)

    def test_se_mandan_todos_en_varios_mensajes(self):
        mensajes = []
        config = {"token": "t", "chat": "c", "tipos": ("cita",)}
        n = avisar.avisar_nuevos(mandar=lambda *a, **k: mensajes.append(a),
                                 config=config, ruta=self.ruta)
        self.assertEqual(n, 400)
        self.assertGreater(len(mensajes), 1, "ha cabido todo en uno: la prueba no prueba nada")
        self.assertEqual(avisos.listar(solo_nuevos=True, ruta=self.ruta), [])

    def test_si_falla_el_envio_lo_que_no_se_mando_sigue_sin_ver(self):
        def falla_a_la_segunda(token, chat, texto, markdown):
            falla_a_la_segunda.veces += 1
            if falla_a_la_segunda.veces > 1:
                raise OSError("sin red")
        falla_a_la_segunda.veces = 0
        config = {"token": "t", "chat": "c", "tipos": ("cita",)}
        n = avisar.avisar_nuevos(mandar=falla_a_la_segunda, config=config, ruta=self.ruta)
        self.assertGreater(n, 0)
        self.assertLess(n, 400)
        self.assertEqual(len(avisos.listar(solo_nuevos=True, ruta=self.ruta)), 400 - n)


class TestDosALaVezNoSePisan(unittest.TestCase):
    """El servidor ya atiende en paralelo: reservar es leer-modificar-escribir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.negocio = negocios.cargar("peluqueria")

    def agenda(self):
        return ag.Agenda("peluqueria", self.negocio.horario,
                         ruta=Path(self._tmp.name) / "agenda.json")

    def test_veinte_reservas_a_la_vez_no_pierden_ninguna(self):
        agenda = self.agenda()
        horas = [f"{h:02d}:{m:02d}" for h in range(10, 14) for m in (0, 15, 30, 45)][:16]
        hilos = [threading.Thread(target=agenda.reservar,
                                  args=("2026-12-24", hora, 15, "Corte de caballero", f"C{i}"))
                 for i, hora in enumerate(horas)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(len(agenda.citas()), len(horas))
        self.assertEqual(len({c["id"] for c in agenda.citas()}), len(horas), "ids repetidos")

    def test_avisos_a_la_vez_no_repiten_id(self):
        ruta = Path(self._tmp.name) / "avisos.json"
        hilos = [threading.Thread(target=avisos.registrar, args=("cita", f"n{i}"),
                                  kwargs={"ruta": ruta}) for i in range(20)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        ids = [a["id"] for a in avisos.listar(ruta=ruta)]
        self.assertEqual(len(ids), 20)
        self.assertEqual(len(set(ids)), 20, "ids repetidos: una escritura pisó a otra")


class TestLlamadasQueNuncaCierran(unittest.TestCase):
    """`/telefono/fin` lo llama el proveedor, y nada garantiza que lo llame."""

    def setUp(self):
        # Esta clase abre llamadas de verdad: escriben en la agenda y en el
        # registro de clientes. Sin aislarlas, le dejan citas puestas a las
        # pruebas del servidor y llamadas contadas a las de telefonía.
        entorno.aislar(self)
        self.reloj = [1000.0]
        self.centralita = telefonia.Centralita(negocios.cargar("peluqueria"),
                                               ahora=lambda: self.reloj[0])

    def test_una_llamada_olvidada_se_cierra_sola_y_deja_su_aviso(self):
        self.centralita.entrada({"CallSid": "CA1", "From": "+34600"}, "https://x/t")
        self.centralita.turno({"CallSid": "CA1", "SpeechResult": "cita para un tinte"}, "https://x/t")
        antes = len(avisos.listar())

        self.reloj[0] += telefonia.Centralita.CADUCA + 1
        self.centralita.entrada({"CallSid": "CA2", "From": "+34601"}, "https://x/t")

        self.assertNotIn("CA1", self.centralita._llamadas, "la conversación sigue en memoria")
        self.assertGreater(len(avisos.listar()), antes, "la cita a medias no se apuntó")

    def test_una_llamada_reciente_no_se_barre(self):
        self.centralita.entrada({"CallSid": "CA1", "From": "+34600"}, "https://x/t")
        self.reloj[0] += 60
        self.centralita.entrada({"CallSid": "CA2", "From": "+34601"}, "https://x/t")
        self.assertIn("CA1", self.centralita._llamadas)


if __name__ == "__main__":
    unittest.main()
