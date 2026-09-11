"""Pruebas de la firma de cada llamada: la única puerta del teléfono.

Esto es lo que separa «una llamada de tu proveedor» de «cualquiera que
haya averiguado la URL». Si se cae, el bot coge citas de quien sea, así
que aquí se prueban las dos formas de colarse: firmar mal, y repetir una
petición buena grabada de antes.

Y lo que más duele y no da la cara: Twilio y Telnyx **no firman igual**.
Poner la credencial de uno creyendo que vale para el otro da 403 en todas
las llamadas sin decir por qué.
"""

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

import ed25519_de_mentira as telnyx  # noqa: E402

from telefono import firmas  # noqa: E402
from telefono import telefonia  # noqa: E402

# Los vectores del RFC 8032, sección 7.1. Si esto pasa, la implementación es
# Ed25519 de verdad y no algo que lo parece.
RFC_8032 = [
    ("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821"
     "590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e"
     "43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b5"
     "38d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]

AHORA = 1757600000.0


class TestEd25519(unittest.TestCase):
    """Contra los vectores del RFC, y por los dos caminos.

    Por los dos porque hay dos: `cryptography` si está instalado y la
    implementación de `firmas.py` si no. Probar solo el que haya en esta
    máquina deja el otro sin mirar justo cuando se usa en la de al lado.
    """

    def test_los_vectores_del_rfc_pasan(self):
        for clave, mensaje, firma in RFC_8032:
            with self.subTest(clave=clave[:8]):
                self.assertTrue(firmas.valida(bytes.fromhex(clave),
                                              bytes.fromhex(mensaje),
                                              bytes.fromhex(firma)))

    def test_los_vectores_pasan_tambien_sin_cryptography(self):
        for clave, mensaje, firma in RFC_8032:
            with self.subTest(clave=clave[:8]):
                self.assertTrue(firmas._valida_a_mano(bytes.fromhex(clave),
                                                      bytes.fromhex(mensaje),
                                                      bytes.fromhex(firma)))

    def test_una_firma_tocada_no_cuela(self):
        clave, mensaje, buena = (bytes.fromhex(x) for x in RFC_8032[1])
        for donde in (0, 31, 32, 63):
            tocada = bytearray(buena)
            tocada[donde] ^= 1
            with self.subTest(byte=donde):
                self.assertFalse(firmas.valida(clave, mensaje, bytes(tocada)))
                self.assertFalse(firmas._valida_a_mano(clave, mensaje, bytes(tocada)))

    def test_otro_mensaje_con_la_misma_firma_no_cuela(self):
        clave, mensaje, buena = (bytes.fromhex(x) for x in RFC_8032[1])
        self.assertFalse(firmas.valida(clave, mensaje + b"y una coma", buena))

    def test_la_clave_de_otro_no_cuela(self):
        _, mensaje, buena = (bytes.fromhex(x) for x in RFC_8032[1])
        ajena = bytes.fromhex(RFC_8032[0][0])
        self.assertFalse(firmas.valida(ajena, mensaje, buena))

    def test_una_firma_que_no_mide_64_no_cuela(self):
        clave, mensaje, buena = (bytes.fromhex(x) for x in RFC_8032[1])
        for corta in (b"", buena[:63], buena + b"\\x00"):
            self.assertFalse(firmas.valida(clave, mensaje, corta))

    def test_una_clave_que_no_mide_32_se_dice(self):
        # Un False aquí dejaría a alguien mirando un 403 sin saber que lo
        # que tiene mal es el .env, no el proveedor.
        _, mensaje, buena = (bytes.fromhex(x) for x in RFC_8032[1])
        for mala in (b"", b"corta", b"x" * 31, b"x" * 33):
            with self.assertRaises(firmas.ClavePublicaMala):
                firmas.valida(mala, mensaje, buena)

    def test_base64_de_basura_no_revienta(self):
        self.assertEqual(firmas.de_base64("esto no es base64 !!"), b"")
        self.assertEqual(firmas.de_base64(""), b"")

    def test_si_cryptography_esta_roto_se_sigue_por_el_otro_lado(self):
        # Pasó de verdad: una instalación a medias levanta un PanicException
        # de Rust, que hereda de BaseException y se escapa de `except
        # Exception`. Una librería opcional no puede tumbar el teléfono.
        antes = firmas._CRYPTOGRAPHY
        firmas._CRYPTOGRAPHY = None
        self.addCleanup(lambda: setattr(firmas, "_CRYPTOGRAPHY", antes))
        clave, mensaje, buena = (bytes.fromhex(x) for x in RFC_8032[1])
        self.assertTrue(firmas.valida(clave, mensaje, buena))


class TestLaFirmaDeTelnyx(unittest.TestCase):
    def setUp(self):
        self.semilla, publica = telnyx.clave(b"la peluqueria")
        import base64
        self.publica = base64.b64encode(publica).decode("ascii")
        self.cuerpo = b"CallSid=CA1&From=%2B34600111222"

    def firmar(self, cuerpo=None, marca=str(int(AHORA))):
        cuerpo = self.cuerpo if cuerpo is None else cuerpo
        import base64
        firma = telnyx.firmar(self.semilla, marca.encode("utf-8") + b"|" + cuerpo)
        return base64.b64encode(firma).decode("ascii"), marca

    def vale(self, **cambios):
        firma, marca = cambios.pop("firmado", self.firmar())
        return telefonia.firma_valida_telnyx(
            cambios.pop("clave", self.publica),
            cambios.pop("cuerpo", self.cuerpo),
            firma, marca, ahora=cambios.pop("ahora", AHORA))

    def test_una_llamada_bien_firmada_entra(self):
        self.assertTrue(self.vale())

    def test_con_el_cuerpo_cambiado_no_entra(self):
        self.assertFalse(self.vale(cuerpo=b"CallSid=CA1&From=%2B34600999999"))

    def test_con_otra_clave_no_entra(self):
        import base64
        _, otra = telnyx.clave(b"otro negocio")
        self.assertFalse(self.vale(clave=base64.b64encode(otra).decode("ascii")))

    def test_sin_firma_o_sin_marca_no_entra(self):
        self.assertFalse(telefonia.firma_valida_telnyx(
            self.publica, self.cuerpo, None, str(int(AHORA)), ahora=AHORA))
        firma, _ = self.firmar()
        self.assertFalse(telefonia.firma_valida_telnyx(
            self.publica, self.cuerpo, firma, None, ahora=AHORA))

    def test_una_peticion_vieja_grabada_no_se_puede_repetir(self):
        # Sin mirar la marca de tiempo, una petición buena capturada vale
        # para siempre y se puede colar la misma llamada mil veces.
        firmado = self.firmar(marca=str(int(AHORA - 600)))
        self.assertFalse(self.vale(firmado=firmado))

    def test_ni_una_del_futuro(self):
        firmado = self.firmar(marca=str(int(AHORA + 600)))
        self.assertFalse(self.vale(firmado=firmado))

    def test_unos_segundos_de_desfase_si_se_aguantan(self):
        # Dos máquinas nunca tienen la misma hora exacta.
        for desfase in (-120, -5, 0, 5, 120):
            with self.subTest(desfase=desfase):
                firmado = self.firmar(marca=str(int(AHORA + desfase)))
                self.assertTrue(self.vale(firmado=firmado))

    def test_una_marca_que_no_es_un_numero_no_revienta(self):
        firma, _ = self.firmar()
        self.assertFalse(telefonia.firma_valida_telnyx(
            self.publica, self.cuerpo, firma, "ayer por la tarde", ahora=AHORA))

    def test_una_clave_mal_pegada_no_revienta(self):
        for mala in ("", "esto no es base64 !!", "aG9sYQ=="):   # la última: 4 bytes
            with self.subTest(clave=mala):
                self.assertFalse(self.vale(clave=mala))


class TestCadaProveedorLoSuyo(unittest.TestCase):
    """Twilio y Telnyx no firman igual, y no se valida «con lo que haya»."""

    def test_se_mira_la_cabecera_que_trae_la_peticion(self):
        self.assertEqual(telefonia.quien_firma({telefonia.CABECERA_TWILIO: "x"}), "twilio")
        self.assertEqual(telefonia.quien_firma({telefonia.CABECERA_TELNYX: "x"}), "telnyx")
        self.assertEqual(telefonia.quien_firma({}), "")

    def test_una_peticion_sin_firma_ninguna_no_es_de_nadie(self):
        # Es el caso que importa: sin cabecera no se elige un validador «por
        # si acaso», se rechaza.
        self.assertEqual(telefonia.quien_firma({"Host": "algo.ts.net"}), "")

    def test_la_firma_de_twilio_no_vale_para_telnyx(self):
        import base64
        semilla, publica = telnyx.clave(b"x")
        cuerpo = b"CallSid=CA1"
        # Una firma con el esquema de Twilio, puesta donde va la de Telnyx.
        de_twilio = telefonia.base64.b64encode(
            telefonia.hmac.new(b"token", b"CallSid=CA1",
                               telefonia.hashlib.sha1).digest()).decode("ascii")
        self.assertFalse(telefonia.firma_valida_telnyx(
            base64.b64encode(publica).decode("ascii"), cuerpo, de_twilio,
            str(int(AHORA)), ahora=AHORA))
        del semilla

    def test_cuales_estan_puestos_de_verdad(self):
        import base64
        _, publica = telnyx.clave(b"x")
        buena = base64.b64encode(publica).decode("ascii")
        self.assertEqual(telefonia.proveedores(
            {"token": "a1b2c3", "clave_publica": buena}), ["twilio", "telnyx"])
        self.assertEqual(telefonia.proveedores(
            {"token": "", "clave_publica": buena}), ["telnyx"])
        self.assertEqual(telefonia.proveedores(
            {"token": "a1b2c3", "clave_publica": ""}), ["twilio"])

    def test_un_hueco_sin_rellenar_no_cuenta_como_puesto(self):
        self.assertEqual(telefonia.proveedores(
            {"token": "<tu API Key de Telnyx>", "clave_publica": ""}), [])
        self.assertEqual(telefonia.proveedores(
            {"token": "", "clave_publica": "<la clave pública de Telnyx>"}), [])

    def test_la_api_key_de_telnyx_en_el_sitio_de_la_clave_no_cuela(self):
        # El error más fácil de cometer: Telnyx da una API Key (KEY0197...)
        # y lo que hace falta es la clave pública. No mide 32 bytes.
        self.assertEqual(telefonia.proveedores(
            {"token": "", "clave_publica": "KEY01973DE066A9C3C1D2E3F4A5B6C7D8"}), [])


if __name__ == "__main__":
    unittest.main()
