"""Todo lo que hace falta ver para saber que le pasa a esta maquina, de una vez.

    python3 diagnostico.py          # el informe entero
    python3 diagnostico.py --corto  # lo justo para `make estado`

Existe para dejar de pegar terminales de doscientas lineas: esto escribe
veinte con lo que importa —que Python, si hay venv, que paquetes, que
modelos hay bajados, si el puerto esta cogido, las ultimas citas y avisos—
y se pega una vez.

**No imprime datos de nadie.** Ni telefonos, ni nombres de clientes, ni IPs,
ni el nombre de la maquina, ni rutas con el usuario dentro. De eso va: es un
informe hecho para pegarse en un chat, y lo que se pega sale de tu control.

Hasta hoy si los imprimia: listaba las ultimas citas **con el nombre de cada
cliente** y los ultimos avisos con su texto, que lleva el telefono de quien
llamo. La prueba que lo vigilaba comprobaba que no salieran IPs ni el
hostname, o sea justo lo que menos importa. Aqui salen cuentas y fechas; el
contenido se mira en la maquina con `python3 avisos.py`.
"""

import argparse
import importlib.metadata
import os
import socket
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _version(paquete: str) -> str:
    try:
        return importlib.metadata.version(paquete)
    except importlib.metadata.PackageNotFoundError:
        return "NO instalado"


def _tam(ruta: Path) -> str:
    total = sum(f.stat().st_size for f in ruta.rglob("*") if f.is_file()) if ruta.exists() else 0
    return f"{total / 1e6:.0f} MB" if total else "no"


def modelos() -> list[str]:
    """Que modelos de voz hay bajados, y cuanto ocupan (a medias se nota)."""
    whisper = Path.home() / ".cache" / "huggingface" / "hub"
    lineas = []
    encontrados = sorted(whisper.glob("models--*whisper*")) if whisper.exists() else []
    if not encontrados:
        lineas.append("whisper: ningun modelo bajado")
    for carpeta in encontrados:
        nombre = carpeta.name.split("--")[-1]
        lineas.append(f"whisper {nombre}: {_tam(carpeta)}")
    piper = Path.home() / ".cache" / "piper"
    voces = sorted(p.stem for p in piper.glob("*.onnx")) if piper.exists() else []
    lineas.append(f"piper: {', '.join(voces) if voces else 'ninguna voz bajada'}")
    return lineas


def puerto_cogido(puerto: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def negocio_y_datos(negocio: str) -> list[str]:
    sys.path.insert(0, str(RAIZ))
    import agenda
    import avisos
    import fechas
    import conocimiento
    import frases
    import memoria
    import negocio as negocios

    lineas = []
    try:
        n = negocios.cargar(negocio)
    except (FileNotFoundError, ValueError) as error:
        return [f"negocio: ❌ {error}"]
    lineas.append(f"negocio: {n.nombre} ({n.ruta.name}) · "
                  f"{len(conocimiento.tarifas(n.conocimiento))} servicios · "
                  f"horario: {'si' if n.horario else 'NO (toma nota, no reserva)'}")
    for problema in frases.problemas(n.conocimiento):
        lineas.append(f"  ⚠️ frases.toml: {problema}")
    faltan = conocimiento.que_falta(n.conocimiento)
    if faltan:
        lineas.append(f"  ⚠️ sin rellenar: {', '.join(faltan)}")

    if n.horario:
        # Cuantas y cuando, nunca de quien. El nombre del cliente no pinta
        # nada en un informe que esta hecho para pegarse.
        citas = agenda.Agenda(n.ruta.name, n.horario).citas()
        proximas = sorted(c["fecha"] for c in citas if c["fecha"] >= fechas.hoy())
        lineas.append(f"citas: {len(citas)} en total, {len(proximas)} por venir"
                      + (f" (la próxima el {proximas[0]})" if proximas else ""))

    # Cuentas, nunca fichas: aqui no sale el telefono ni el nombre de nadie.
    cuentas = memoria.cuentas()
    lineas.append(f"clientes: {cuentas['fichas']} fichas · "
                  f"{cuentas['con_nombre']} con nombre · "
                  f"{cuentas['repiten']} repiten · "
                  f"{cuentas['con_costumbre']} con servicio habitual")

    todos = avisos.listar()
    por_tipo = {}
    for a in todos:
        por_tipo[a["tipo"]] = por_tipo.get(a["tipo"], 0) + 1
    sin_ver = sum(1 for a in todos if not a.get("visto"))
    lineas.append(f"avisos: {len(todos)} en total, {sin_ver} sin ver"
                  + (f" · {', '.join(f'{k} {v}' for k, v in sorted(por_tipo.items()))}"
                     if por_tipo else ""))
    if todos:
        lineas.append(f"  el último, {todos[0]['fecha']} {todos[0]['hora']} "
                      f"[{todos[0]['tipo']}] — el texto no se imprime: "
                      "míralo con `python3 avisos.py`")
    return lineas


def informe(negocio: str, puerto: int, corto: bool, puerto_telefono: int = 8081) -> str:
    en_venv = sys.prefix != sys.base_prefix
    lineas = [
        f"python {sys.version.split()[0]} · {'venv' if en_venv else 'SIN venv'}",
        f"faster-whisper {_version('faster-whisper')} · piper-tts {_version('piper-tts')} · "
        f"onnxruntime {_version('onnxruntime')} · ctranslate2 {_version('ctranslate2')}",
        *modelos(),
        f"puerto {puerto} (demo, solo tailnet): "
        f"{'cogido (¿el servidor?)' if puerto_cogido(puerto) else 'libre'}",
    ]
    import telefonia
    if telefonia.configuracion() is None:
        lineas.append("teléfono: sin token, el webhook no arranca")
    else:
        lineas.append(f"puerto {puerto_telefono} (teléfono, público si hay funnel): "
                      f"{'cogido' if puerto_cogido(puerto_telefono) else 'libre'}")
    if corto:
        return "\n".join(lineas + negocio_y_datos(negocio)[:1])

    lineas += ["", *negocio_y_datos(negocio)]
    servicio = Path.home() / ".config" / "systemd" / "user" / "gjallarhorn.service"
    lineas += ["", f"servicio systemd: {'instalado' if servicio.exists() else 'no instalado (make arrancar)'}"]
    # La ruta entera lleva el usuario y el layout de la maquina dentro.
    lineas.append("datos en: " + ("la carpeta de GJALLARHORN_DATOS"
                                  if os.environ.get("GJALLARHORN_DATOS")
                                  else "datos/ dentro del repo"))
    return "\n".join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Que le pasa a esta maquina")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--puerto", type=int, default=8080)
    parser.add_argument("--puerto-telefono", type=int, default=8081)
    parser.add_argument("--corto", action="store_true")
    args = parser.parse_args()
    print(informe(args.negocio, args.puerto, args.corto, args.puerto_telefono))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
