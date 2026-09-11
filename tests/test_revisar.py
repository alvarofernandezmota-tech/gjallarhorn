"""Pruebas de la orden que dice si el bot está listo para coger llamadas.

Lo que se vigila aquí es la diferencia entre **fallo** y **aviso**: un fallo
es lo que hace que una llamada salga mal —sin tarifas no hay precios, sin
token no hay webhook— y un aviso es lo que funciona pero conviene mirar. Si
todo fuera fallo, nadie miraría la lista; si nada lo fuera, no serviría de
nada.
"""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

import avisos  # noqa: E402
import copias  # noqa: E402
import datos  # noqa: E402
import frases as _frases  # noqa: E402
import negocio as negocios  # noqa: E402
import revisar as _revisar  # noqa: E402

HOY = date(2026, 9, 11)


class CasoRevisar(unittest.TestCase):
    def setUp(self):
        entorno.aislar(self)
        datos.olvidar()
        self.addCleanup(datos.olvidar)
        _frases.olvidar()
        self.addCleanup(_frases.olvidar)
        datos.usar("peluqueria")
        self.negocio = negocios.cargar("peluqueria")

    def puntos(self, negocio=None):
        return _revisar.revisar(negocio or self.negocio, hoy=HOY)

    def titulos(self, marca=None, negocio=None):
        return [p.titulo for p in self.puntos(negocio)
                if marca is None or p.marca == marca]

    def negocio_a_medias(self, **ficheros):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        carpeta = Path(tmp.name) / "a-medias"
        carpeta.mkdir()
        for nombre, texto in ficheros.items():
            (carpeta / nombre.replace("_", ".")).write_text(texto, encoding="utf-8")
        return negocios.cargar(carpeta)


class TestLoQueEsUnFallo(CasoRevisar):
    def test_sin_tarifas_no_esta_listo(self):
        vacio = self.negocio_a_medias(faq_md="**¿Horario?**\nDe 10 a 20.\n")
        rotos = [p for p in self.puntos(vacio) if p.roto]
        self.assertTrue(any("tarifas" in p.titulo for p in rotos))

    def test_un_frases_toml_roto_es_un_fallo(self):
        negocio = self.negocio_a_medias(
            tarifas_md="| Servicio | Precio |\n|---|---|\n| Corte | 10 € |\n",
            frases_toml='[dice]\npide_dia = "¿Qué día {fehca}?"\n')
        _frases.olvidar()
        rotos = [p for p in self.puntos(negocio) if p.roto]
        self.assertTrue(any("frases.toml" in p.titulo for p in rotos),
                        [p.titulo for p in self.puntos(negocio)])

    def test_sin_token_de_telefono_no_esta_listo(self):
        # En las pruebas nunca hay token: el webhook no puede arrancar.
        self.assertTrue(any("teléfono" in t for t in self.titulos(_revisar.FALLO)))


class TestLoQueEsSoloUnAviso(CasoRevisar):
    def test_sin_horario_se_avisa_pero_no_se_rompe(self):
        negocio = self.negocio_a_medias(
            tarifas_md="| Servicio | Precio |\n|---|---|\n| Corte | 10 € |\n")
        puntos = self.puntos(negocio)
        horario = next(p for p in puntos if "horario" in p.titulo)
        self.assertEqual(horario.marca, _revisar.AVISO)
        self.assertFalse(horario.roto)

    def test_sin_copias_se_avisa(self):
        self.assertTrue(any("copias" in t for t in self.titulos(_revisar.AVISO)))

    def test_con_la_copia_de_hoy_se_pone_en_verde(self):
        copias.hacer(hoy=HOY)
        avisos.registrar("llamada", "algo")     # para que haya algo que copiar
        copias.hacer(hoy=HOY)
        self.assertTrue(any("copias: la de hoy" in t for t in self.titulos(_revisar.BIEN)))

    def test_las_preguntas_repetidas_sin_contestar_salen(self):
        for _ in range(2):
            avisos.registrar("fallo", "Recado: «¿hacéis uñas?»",
                             {"falta": "respuesta", "frase": "¿hacéis uñas?"})
        dicho = " ".join(self.titulos(_revisar.AVISO) +
                         [p.detalle for p in self.puntos()])
        self.assertIn("uñas", dicho)

    def test_una_sola_vez_no_sale(self):
        avisos.registrar("fallo", "Recado: «¿hacéis uñas?»",
                         {"falta": "respuesta", "frase": "¿hacéis uñas?"})
        self.assertTrue(any("no hay preguntas repetidas" in t
                            for t in self.titulos(_revisar.BIEN)))


class TestLaMezclaDeTratos(CasoRevisar):
    def test_un_bot_con_frases_del_otro_lado_se_avisa(self):
        negocio = self.negocio_a_medias(
            tarifas_md="| Servicio | Precio |\n|---|---|\n| Corte | 10 € |\n",
            frases_toml='[dice]\npide_dia = "¿Qué día te viene bien?"\n'
                        'pide_nombre = "¿A nombre de quién te la apunto?"\n')
        _frases.olvidar()
        aviso = next(p for p in self.puntos(negocio) if p.titulo.startswith("frases:"))
        self.assertEqual(aviso.marca, _revisar.AVISO)
        self.assertIn("trata de tú", aviso.titulo)
        self.assertIn("make frases", aviso.detalle)

    def test_el_de_ejemplo_no_mezcla(self):
        self.assertIn("frases: trata de usted en todo", self.titulos(_revisar.BIEN))


class TestLaOrden(CasoRevisar):
    def correr(self, *argumentos):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = _revisar.main(list(argumentos))
        return codigo, salida.getvalue()

    def test_sale_1_cuando_algo_esta_roto(self):
        codigo, dicho = self.correr()
        self.assertEqual(codigo, 1, dicho)
        self.assertIn("No está listo", dicho)

    def test_un_negocio_que_no_existe_se_dice_y_no_revienta(self):
        codigo, dicho = self.correr("--negocio", "no-existe")
        self.assertEqual(codigo, 1)
        self.assertIn("no encuentro el negocio", dicho)

    def test_con_telefono_configurado_sale_0(self):
        import telefonia
        antes = telefonia.configuracion
        telefonia.configuracion = lambda: {"token": "secreto", "voz": "Polly.Lucia"}
        self.addCleanup(lambda: setattr(telefonia, "configuracion", antes))
        codigo, dicho = self.correr()
        self.assertEqual(codigo, 0, dicho)
        self.assertIn("Listo para coger llamadas", dicho)


if __name__ == "__main__":
    unittest.main()
