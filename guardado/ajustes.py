"""De donde salen los ajustes: el `.env` de quien despliega el bot.

Esto vivia dentro de `avisar.py`, que es el modulo de mandar avisos por
Telegram. Leer configuracion y mandar un mensaje al movil no son la misma
cosa, y juntarlas obligaba al cerebro a importar el notificador solo para
enterarse de si hay una clave de LLM puesta.

## Por que el fichero se busca desde el directorio de trabajo

La tentacion es `Path(__file__).parent.parent / ".env"`, y esta mal: este
modulo puede vivir dentro de una libreria compartida, y entonces esa ruta
apunta a la libreria y no a la aplicacion que la usa. El `.env` es de quien
**despliega**, no de quien programa.

Asi que se busca en el directorio de trabajo, que es el sitio correcto: las
tres unidades de systemd fijan `WorkingDirectory` en la raiz del repo, y las
ordenes de `make` corren desde ahi. Y se puede decir a mano con
`GJALLARHORN_ENV` para los casos raros.
"""

import os
from pathlib import Path

VARIABLE = "GJALLARHORN_ENV"


def fichero() -> Path:
    """Donde esta el .env ahora mismo. Se resuelve al llamar, nunca antes.

    Estuvo en un argumento por defecto, que Python evalua una vez al definir
    la funcion: cambiarlo despues no cambiaba nada y las pruebas no podian
    apartarse del .env de verdad. Un valor por defecto que es una ruta
    calculada es siempre una trampa esperando.
    """
    puesto = os.environ.get(VARIABLE, "").strip()
    return Path(puesto).expanduser() if puesto else Path.cwd() / ".env"


def _pares(fich: Path) -> list[tuple[str, str]]:
    """Los KEY=VALOR del fichero, en orden y con las repeticiones."""
    if not fich.exists():
        return []
    pares = []
    for linea in fich.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        pares.append((clave.strip(), valor.strip().strip("'\"")))
    return pares


def leer(fich: Path | None = None) -> None:
    """Carga KEY=VALOR del .env al entorno, sin pisar lo que ya este puesto.

    Si una clave sale dos veces vale la ULTIMA, como hace systemd con
    `EnvironmentFile=`. Leyendolo al reves, `revisar` veia una credencial y
    el servicio arrancaba con otra, y eso no se ve por ningun lado: las
    llamadas se caen con un 403 y todo sale en verde.
    """
    ultimo = dict(_pares(fichero() if fich is None else fich))
    for clave, valor in ultimo.items():
        os.environ.setdefault(clave, valor)      # el entorno de verdad manda


def poner(clave: str, valor: str, fich: Path | None = None) -> str:
    """Deja `clave=valor` en el .env. Devuelve «puesta», «cambiada» o «igual».

    **Sustituye** las que hubiera en vez de anadir otra linea. Anadir es lo
    que sale de un `echo >>`, y asi es como acaba un .env con la misma clave
    tres veces: con systemd gana la ultima, o sea que la que acabas de poner
    puede no ser la que se use.
    """
    fich = fichero() if fich is None else fich
    linea = f"{clave}={valor}"
    lineas = fich.read_text(encoding="utf-8").splitlines() if fich.exists() else []
    donde = [i for i, ya in enumerate(lineas) if ya.strip().startswith(f"{clave}=")]
    if not donde:
        if lineas and lineas[-1].strip():
            lineas.append("")
        lineas.append(linea)
        que = "puesta"
    else:
        que = "igual" if lineas[donde[0]] == linea else "cambiada"
        lineas[donde[0]] = linea
        for sobra in reversed(donde[1:]):        # las repetidas, fuera
            del lineas[sobra]
            que = "cambiada"
    fich.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return que


def quitar(clave: str, fich: Path | None = None) -> int:
    """Quita esa clave del .env. Lo comentado no se toca: es documentacion."""
    fich = fichero() if fich is None else fich
    if not fich.exists():
        return 0
    lineas = fich.read_text(encoding="utf-8").splitlines()
    quedan = [linea for linea in lineas
              if not linea.strip().startswith(f"{clave}=")]
    if len(quedan) != len(lineas):
        fich.write_text("\n".join(quedan) + "\n", encoding="utf-8")
    return len(lineas) - len(quedan)


def repetidas(fich: Path | None = None) -> list[str]:
    """Claves puestas mas de una vez. Vale la ultima, pero conviene saberlo."""
    visto, repes = set(), []
    for clave, _ in _pares(fichero() if fich is None else fich):
        if clave in visto and clave not in repes:
            repes.append(clave)
        visto.add(clave)
    return repes
