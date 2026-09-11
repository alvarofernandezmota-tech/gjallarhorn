"""Ed25519: comprobar una firma. Solo comprobar.

Hace falta para el webhook de Telnyx, que firma cada aviso con su clave
privada y publica la publica. Twilio usa otra cosa —un HMAC-SHA1 con el
Auth Token, que es `hmac` de la libreria estandar— y eso ya estaba.

## Por que a mano

Python no trae Ed25519 en la libreria estandar, y este repo no tiene
dependencias en el camino de una llamada: el webhook tiene que arrancar en
un clon recien hecho, sin `pip install` de nada. Si `cryptography` esta
instalado se usa ese —esta auditado y es mucho mas rapido—, y si no, la
implementacion de aqui abajo, que es la de referencia del RFC 8032.

Escribir criptografia a mano casi siempre es mala idea, y conviene decir
por que aqui no lo es: esto **solo verifica**. No hay clave privada, no se
firma nada y no se guarda ningun secreto: la clave publica y la firma son
publicas por definicion. Lo que hace peligrosa una implementacion casera
—que el tiempo que tarda filtre el secreto que maneja— aqui no aplica,
porque no maneja ninguno. Y lo que si importa, que acepte exactamente las
firmas buenas y rechace las malas, se comprueba contra los vectores del
propio RFC 8032 en las pruebas.

Lo que NO hay que hacer con esto es firmar, generar claves ni meterle nada
secreto. Para eso, `cryptography`.
"""

import hashlib

__all__ = ["valida", "de_base64", "ClavePublicaMala"]

P = 2**255 - 19                                    # el cuerpo primo
L = 2**252 + 27742317777372353535851937790883648493   # el orden del grupo
D = -121665 * pow(121666, P - 2, P) % P
RAIZ_MENOS_UNO = pow(2, (P - 1) // 4, P)


class ClavePublicaMala(ValueError):
    """La clave publica no son 32 bytes o no es un punto de la curva."""


def _recuperar_x(y: int, signo: int) -> int | None:
    """La x del punto a partir de la y. None si esa y no esta en la curva."""
    if y >= P:
        return None
    u = (y * y - 1) % P
    v = (D * y * y + 1) % P
    # x = (u/v)^((p+3)/8), que con p = 5 mod 8 se calcula asi sin dividir.
    x = u * pow(v, 3, P) * pow(u * pow(v, 7, P), (P - 5) // 8, P) % P
    if (v * x * x - u) % P == 0:
        pass
    elif (v * x * x + u) % P == 0:
        x = x * RAIZ_MENOS_UNO % P
    else:
        return None
    if x == 0 and signo:
        return None                                 # -0 no es una codificacion valida
    return P - x if signo != x & 1 else x


def _sumar(punto, otro):
    """Suma en coordenadas extendidas, que evita dividir en cada paso."""
    x1, y1, z1, t1 = punto
    x2, y2, z2, t2 = otro
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = 2 * t1 * t2 * D % P
    e = 2 * z1 * z2 % P
    f, g, h, i = (b - a) % P, (e - c) % P, (e + c) % P, (b + a) % P
    return (f * g % P, h * i % P, g * h % P, f * i % P)


def _por(punto, cuantas: int):
    """El punto sumado `cuantas` veces, doblando."""
    resultado = (0, 1, 1, 0)                        # el neutro
    while cuantas > 0:
        if cuantas & 1:
            resultado = _sumar(resultado, punto)
        punto = _sumar(punto, punto)
        cuantas >>= 1
    return resultado


def _descomprimir(treinta_y_dos: bytes):
    """Los 32 bytes de un punto -> el punto. None si no lo son."""
    if len(treinta_y_dos) != 32:
        return None
    entero = int.from_bytes(treinta_y_dos, "little")
    y, signo = entero & ((1 << 255) - 1), entero >> 255
    x = _recuperar_x(y, signo)
    return None if x is None else (x, y, 1, x * y % P)


# El punto base, tal cual viene en el RFC 8032.
_BASE_X = 15112221349535400772501151409588531511454012693041857206046113283949847762202
_BASE_Y = 46316835694926478169428394003475163141307993866256225615783033603165251855960
_BASE = (_BASE_X, _BASE_Y, 1, _BASE_X * _BASE_Y % P)


def _iguales(punto, otro) -> bool:
    """Dos puntos proyectivos son el mismo si cruzan igual."""
    x1, y1, z1, _ = punto
    x2, y2, z2, _ = otro
    return (x1 * z2 - x2 * z1) % P == 0 and (y1 * z2 - y2 * z1) % P == 0


def _valida_a_mano(clave: bytes, mensaje: bytes, firma: bytes) -> bool:
    if len(firma) != 64:
        return False
    a = _descomprimir(clave)
    if a is None:
        raise ClavePublicaMala("la clave publica no es un punto de la curva")
    r = _descomprimir(firma[:32])
    s = int.from_bytes(firma[32:], "little")
    if r is None or s >= L:
        return False                                # firma maleable o mal formada
    k = int.from_bytes(hashlib.sha512(firma[:32] + clave + mensaje).digest(),
                       "little") % L
    return _iguales(_por(_BASE, s), _sumar(r, _por(a, k)))


_CRYPTOGRAPHY = "sin mirar"      # se mira una vez, no en cada llamada


def _cargar_cryptography():
    """(Ed25519PublicKey, InvalidSignature), o None si no se puede usar.

    Se guarda el resultado: si la libreria esta rota, intentar importarla
    en cada webhook escupe el panico de Rust por stderr cada vez y deja el
    log inservible justo cuando hay llamadas.
    """
    global _CRYPTOGRAPHY
    if _CRYPTOGRAPHY != "sin mirar":
        return _CRYPTOGRAPHY
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        _CRYPTOGRAPHY = (Ed25519PublicKey, InvalidSignature)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:        # noqa: BLE001 - una opcional rota no tumba el telefono
        _CRYPTOGRAPHY = None
    return _CRYPTOGRAPHY


def _con_cryptography(clave: bytes, mensaje: bytes, firma: bytes) -> bool | None:
    """El camino rapido. None si la libreria no esta o no se puede usar.

El `except BaseException` no es pereza, y el `BaseException` tampoco.
    `cryptography` lleva una parte compilada, y una instalacion a medias
    —falta `_cffi_backend`, la rueda es de otra arquitectura, el sistema se
    actualizo por debajo— no levanta ImportError: levanta lo que le salga
    de dentro de Rust. Aqui mismo salio un `pyo3_runtime.PanicException`,
    que **hereda de BaseException**, asi que un `except Exception` lo deja
    pasar igual. Dejar que suba tumbaria el webhook entero por una libreria
    que era *opcional*. Ctrl+C y `sys.exit` se vuelven a lanzar: eso si es
    de quien manda, no de la libreria.
    """
    cargado = _cargar_cryptography()
    if cargado is None:
        return None
    Ed25519PublicKey, InvalidSignature = cargado
    try:
        publica = Ed25519PublicKey.from_public_bytes(clave)
    except ValueError as error:
        raise ClavePublicaMala(str(error)) from error
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:        # noqa: BLE001 - lo mismo, pero al usarla
        return None
    try:
        publica.verify(firma, mensaje)
    except InvalidSignature:
        return False
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:        # noqa: BLE001
        return None
    return True


def valida(clave: bytes, mensaje: bytes, firma: bytes) -> bool:
    """¿Firmo esta clave este mensaje?

    Levanta ClavePublicaMala si la clave no vale: eso es un fallo de
    configuracion, no un intento de colarse, y taparlo devolviendo False
    dejaria a alguien mirando un 403 sin saber que la clave esta mal.
    """
    if len(clave) != 32:
        raise ClavePublicaMala(f"la clave publica son 32 bytes, no {len(clave)}")
    rapido = _con_cryptography(clave, mensaje, firma)
    return _valida_a_mano(clave, mensaje, firma) if rapido is None else rapido


def de_base64(texto: str) -> bytes:
    """Lo que se pega del portal del proveedor -> bytes. b'' si no vale."""
    import base64
    import binascii
    try:
        return base64.b64decode(texto.strip(), validate=True)
    except (binascii.Error, ValueError):
        return b""
