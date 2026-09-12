"""`make lanzar`: de aqui a la primera llamada, sin sitios donde tropezar.

Los pasos para dar un numero de telefono a un negocio estan repartidos en
cinco sitios —el `.env`, systemd, tailscale, el portal del proveedor y el
log— y entre paso y paso hay que copiar cosas de uno a otro. Cada copia es
un sitio donde equivocarse, y los errores de aqui no dan la cara: el
webhook arranca igual y luego **todas** las llamadas se caen con un 403.

Asi que esto hace los pasos por orden, comprueba cada uno antes de seguir,
y **nunca imprime un hueco que haya que rellenar a mano**: si hace falta la
clave del proveedor, la pide y la comprueba antes de escribirla; si hace
falta la URL publica, se la pregunta a tailscale. Los `<...>` de una guia
pegados tal cual son un error que ya ha costado una tarde.

No hace nada a escondidas: cada orden que va a correr se enseña antes.
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

from hugin.guardado import avisos
from hugin.guardado import ajustes
from hugin.guardado import datos
from hugin.negocio import negocio as negocios
from dueno import revisar as _revisar
from telefono import telefonia
from telefono import urlpublica

RAIZ = Path(__file__).resolve().parent.parent
CLAVE_TELNYX = "GJALLARHORN_TELEFONO_CLAVE_PUBLICA"
TOKEN_TWILIO = "GJALLARHORN_TELEFONO_TOKEN"


def _titulo(numero: int, texto: str) -> None:
    print(f"\n\033[1m{numero}. {texto}\033[0m")


def _correr(orden: list[str], ensenar: bool = True) -> subprocess.CompletedProcess:
    """Corre una orden **enseñandola antes**. Nada pasa a escondidas."""
    if ensenar:
        print(f"   $ {' '.join(orden)}")
    try:
        return subprocess.run(orden, capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return subprocess.CompletedProcess(orden, 127, "", str(error))


# ---- 1. con que se comprueba la firma -----------------------------------

def _que_clave_es(dicho: str) -> tuple[str, str] | None:
    """Adivina si lo pegado es de Twilio o de Telnyx. None si no es ninguna.

    No es por comodidad: el error mas facil es poner la API Key de Telnyx
    donde va la clave publica, y las dos son cadenas raras que a ojo se
    parecen. Aqui se mira lo que son.
    """
    dicho = dicho.strip()
    if not dicho or telefonia.token_de_mentira(dicho):
        return None
    from telefono import firmas
    if len(firmas.de_base64(dicho)) == 32:
        return CLAVE_TELNYX, "la clave publica de Telnyx"
    # Lo que da cada proveedor y NO vale, con su pinta, para poder decirlo
    # por su nombre. Enterarse de que has pegado el identificador en vez del
    # secreto es la diferencia entre diez segundos y una tarde.
    if _es_un_sid_de_twilio(dicho) or dicho.upper().startswith("KEY"):
        return None
    if len(dicho) == 32 and all(c in "0123456789abcdefABCDEF" for c in dicho):
        return TOKEN_TWILIO, "el Auth Token de Twilio"
    return None


def _es_un_sid_de_twilio(dicho: str) -> bool:
    """«AC» y 32 hex: el Account SID, que es el identificador, no el secreto.

    Estan pegados el uno al otro en la consola y el Auth Token ademas viene
    tapado tras un boton «Show», asi que copiar el de arriba es lo normal.
    """
    return (len(dicho) == 34 and dicho[:2].upper() == "AC"
            and all(c in "0123456789abcdefABCDEF" for c in dicho[2:]))


def _pedir_la_clave() -> str | bool:
    print("   Hace falta con que comprobar la firma de cada llamada. Segun tu proveedor:")
    print("     Telnyx  la CLAVE PUBLICA, en el portal:")
    print("             Keys & Credentials > Public Key")
    print("             (NO la API Key. La API Key aqui no vale para nada.)")
    print("     Twilio  el Auth Token de la consola.")
    print()
    try:
        dicho = input("   Pegala aqui (Enter para dejarlo): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not dicho:
        print("   Lo dejamos. Cuando la tengas, «make lanzar» otra vez.")
        return False

    cual = _que_clave_es(dicho)
    if cual is None:
        print("\n   ❌ Eso no es ninguna de las dos, asi que no lo escribo.")
        if _es_un_sid_de_twilio(dicho):
            print("      Eso es el Account SID de Twilio (empieza por AC): es el")
            print("      identificador de tu cuenta, no el secreto con el que firma.")
            print("      El Auth Token esta JUSTO DEBAJO en la consola, tapado tras")
            print("      un boton «Show». Son 32 hex, sin el AC delante.")
        elif dicho.upper().startswith("KEY"):
            print("      Parece una API Key de Telnyx (empieza por KEY). Lo que hace")
            print("      falta es la clave PUBLICA: Keys & Credentials > Public Key.")
        elif "<" in dicho or ">" in dicho:
            print("      Los <...> de una guia son un hueco, no parte de la clave.")
        else:
            print("      La de Telnyx es base64 de 32 bytes; la de Twilio, 32 hex.")
        return False

    variable, comoSeLlama = cual
    que = ajustes.poner(variable, dicho)
    print(f"\n   ✅ Guardada {comoSeLlama} en .env ({que}).")
    print("      El .env esta en el .gitignore: no se sube.")
    import os
    os.environ[variable] = dicho        # para que el resto de esta orden la vea
    return que                          # «puesta» / «cambiada» / «igual»


def paso_la_firma() -> str | bool:
    _titulo(1, "Con que se comprueba que la llamada es de tu proveedor")
    config = telefonia.configuracion()
    puestos = telefonia.proveedores(config) if config else []
    if puestos:
        print(f"   ✅ Ya esta: {' y '.join(puestos)}.")
        return "ya estaba"
    if config and not puestos:
        print("   ⚠️  Hay algo en el .env pero no sirve.")
        for punto in _revisar._el_telefono():
            print(f"      {punto.titulo}")
            if punto.detalle:
                print(f"      {punto.detalle}")
        _barrer_los_huecos(config)
        print()
    return _pedir_la_clave()


def _barrer_los_huecos(config: dict) -> None:
    """Borra del .env las credenciales que son el hueco del ejemplo.

    Quejarse de una linea muerta y dejarla ahi es dar trabajo: obliga a
    salir, editar el fichero a mano y volver. Y mientras siga puesta,
    `revisar` la seguira sacando en rojo aunque ya hayas puesto la buena
    del otro proveedor, que confunde mas todavia.

    Solo se borra lo que es de relleno —`<...>`, `pon-aqui-el-token`—, que
    no vale para nada y no hay nada que perder. Una credencial de verdad no
    se toca nunca, aunque sea del proveedor que no usas.
    """
    import os
    for variable, valor in ((TOKEN_TWILIO, config.get("token")),
                            (CLAVE_TELNYX, config.get("clave_publica"))):
        if valor and telefonia.token_de_mentira(valor):
            ajustes.quitar(variable)
            os.environ.pop(variable, None)
            print(f"      → he borrado {variable} del .env: era el hueco del")
            print("        ejemplo sin rellenar, no servia para nada.")


# ---- 2. lo demas del negocio --------------------------------------------

def paso_el_negocio(negocio) -> bool:
    _titulo(2, "El negocio: precios, horario y lo que sabe contestar")
    roto = False
    for punto in _revisar.revisar(negocio):
        if punto.titulo.startswith("teléfono"):
            continue                     # ese es el paso 1
        if punto.roto:
            roto = True
            print(f"   {punto.marca} {punto.titulo}")
            if punto.detalle:
                print(f"      {punto.detalle}")
    if roto:
        print("\n   Con esto roto el bot cogeria llamadas y contestaria mal.")
        return False
    print("   ✅ Sin nada roto. («make revisar» lo cuenta entero.)")
    return True


# ---- 3. el servidor -----------------------------------------------------

def _servicio_activo() -> bool:
    """¿Esta ya corriendo la unidad? Un `enable --now` sobre algo activo
    no lo reinicia, y entonces no relee el .env."""
    return _correr(["systemctl", "--user", "is-active", "--quiet", "gjallarhorn"],
                   ensenar=False).returncode == 0


def _vivo(puerto: int) -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def paso_el_servidor(puerto: int, recien_puesta: bool = False) -> bool:
    """Deja el servicio escuchando el puerto del telefono.

    `recien_puesta` dice si el paso 1 acaba de escribir la credencial. Si lo
    hizo hay que **reiniciar**, no arrancar: un servicio que ya estaba
    corriendo leyo el .env cuando arranco, y `systemctl enable --now` sobre
    algo ya activo no hace nada. Eso dejaba el token nuevo sin leer y el
    puerto del telefono sin abrir, diciendo «ha arrancado pero no escucha»
    sin explicar que lo que faltaba era reiniciar. Es el caso normal, no el
    raro: el paso 1 escribe la credencial y el 3 la necesita.
    """
    _titulo(3, "El servidor, encendido y que siga encendido")
    if _vivo(puerto) and not recien_puesta:
        print(f"   ✅ Ya hay algo escuchando en el {puerto}.")
        return True
    if not shutil.which("systemctl") or not shutil.which("make"):
        print("   ⚠️  Sin systemctl aqui. Arrancalo a mano en otra terminal:")
        print("      make servidor")
        return False
    # `make` y no `systemctl` a secas: la unidad se genera de una plantilla,
    # y en una maquina nueva todavia no existe. Las dos ordenes la crean.
    if recien_puesta or _servicio_activo():
        print("   El servicio ya estaba en marcha: lo reinicio para que lea")
        print("   el .env de ahora.")
        hecho = _correr(["make", "reiniciar"])
    else:
        hecho = _correr(["make", "arrancar"])
    if hecho.returncode != 0:
        print(f"   ❌ No ha arrancado: {(hecho.stderr or hecho.stdout).strip()[:300]}")
        return False
    for _ in range(20):
        if _vivo(puerto):
            print(f"   ✅ Escuchando en el {puerto}, y vuelve a arrancar si se cae.")
            _avisar_del_linger()
            return True
        time.sleep(0.5)
    print("   ❌ Ha arrancado pero no escucha. «make log» dice por que.")
    return False


def _avisar_del_linger() -> None:
    """Sin linger el servicio se muere al cerrar sesion. Con un telefono, eso
    es el bot muerto a las tantas y nadie cogiendo las llamadas."""
    import os
    quien = os.environ.get("USER") or ""
    hecho = _correr(["loginctl", "show-user", quien], ensenar=False)
    if "Linger=yes" in (hecho.stdout or ""):
        return
    print("   ⚠️  Le falta el «linger»: al cerrar sesion se pararia, y con el")
    print("      telefono puesto eso es quedarse sin cogerlas. Una vez y ya:")
    print(f"      sudo loginctl enable-linger {quien}")


# ---- 4. la puerta a internet --------------------------------------------

def paso_la_puerta(puerto: int) -> str | None:
    _titulo(4, "Publicar SOLO el webhook del telefono")
    if not shutil.which("tailscale"):
        print("   ⚠️  Sin tailscale no se puede publicar desde aqui.")
        return None
    hecho = _correr(["tailscale", "funnel", "--bg", str(puerto)])
    if hecho.returncode != 0:
        print(f"   ❌ {(hecho.stderr or hecho.stdout).strip()[:300]}")
        return None
    raiz = urlpublica.base()
    if raiz == urlpublica.GENERICA:
        print("   ⚠️  Publicado, pero no se como se llama esta maquina.")
        print("      «tailscale status» te lo dice.")
        return None
    print(f"   ✅ Publicado el {puerto}, que sirve SOLO /telefono/*.")
    print("      El puerto de la demo y del panel no sale de tu tailnet.")
    return raiz


# ---- 5. el proveedor ----------------------------------------------------

def paso_el_proveedor(raiz: str | None) -> None:
    _titulo(5, "Pegar esto en el portal de tu proveedor")
    if raiz is None:
        print("   Sin la URL publica no hay nada que pegar todavia.")
        return
    print("   Telnyx: una aplicacion TeXML (NO Call Control: el bot habla TwiML),")
    print("   y el numero asignado a esa aplicacion. Twilio: en el numero.")
    print()
    print(f"     Webhook de voz    {raiz}/telefono/entrada")
    print(f"     Status callback   {raiz}/telefono/fin")
    print()
    print("   Estan enteras: se copian y se pegan, no hay nada que cambiar.")


# ---- 6. la llamada ------------------------------------------------------

def paso_la_llamada(negocio, espera: int = 300) -> bool:
    _titulo(6, "Llama a tu numero")
    print(f"   Te escucho hasta {espera // 60} minutos. Ctrl+C para dejarlo.")
    print("   (El bot ya funciona sin mi: esto solo te lo cuenta en vivo.)\n")
    antes = {a["id"] for a in avisos.listar()}
    hasta = time.time() + espera
    try:
        while time.time() < hasta:
            nuevos = [a for a in avisos.listar() if a["id"] not in antes]
            for aviso in reversed(nuevos):
                print(f"   📞 {aviso['hora']}  {aviso['texto']}")
                antes.add(aviso["id"])
            if nuevos:
                print("\n   ✅ Ha entrado. El bot esta cogiendo llamadas.")
                print("      «make panel» para ver el dia; «make log» para el detalle.")
                return True
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n   Lo dejamos de mirar. El bot sigue cogiendo llamadas.")
        return False
    print("   No ha entrado ninguna. Si llamaste y no salio nada, «make log»:")
    print("   un «firma no valida» quiere decir que la clave del .env no es la buena.")
    return False


def main(argumentos: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="De aqui a la primera llamada")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--puerto", type=int, default=8081)
    parser.add_argument("--sin-esperar", action="store_true",
                        help="no quedarse mirando a que entre la llamada")
    parser.add_argument("--espera", type=int, default=300)
    args = parser.parse_args(argumentos)

    try:
        negocio = negocios.cargar(args.negocio)
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return 1
    datos.usar(negocio)

    print(f"\033[1mPoner al telefono a «{negocio.nombre}»\033[0m")
    # Lo que devuelve dice si ACABA de escribirse la credencial, y de eso
    # depende que el paso 3 reinicie en vez de arrancar.
    que_paso = paso_la_firma()
    if not que_paso:
        return 1
    recien_puesta = que_paso in ("puesta", "cambiada")
    if not paso_el_negocio(negocio):
        return 1
    if not paso_el_servidor(args.puerto, recien_puesta):
        return 1
    raiz = paso_la_puerta(args.puerto)
    paso_el_proveedor(raiz)
    if args.sin_esperar or raiz is None:
        print("\nCuando lo tengas puesto en el proveedor, llama y mira «make log».")
        return 0
    paso_la_llamada(negocio, args.espera)
    return 0


if __name__ == "__main__":
    sys.exit(main())
