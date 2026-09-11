"""Todo lo que hace falta ver para saber que le pasa a esta maquina, de una vez.

    python3 diagnostico.py          # el informe entero
    python3 diagnostico.py --corto  # lo justo para `make estado`

Existe para dejar de pegar terminales de doscientas lineas: esto escribe
veinte con lo que importa —que Python, si hay venv, que paquetes, que
modelos hay bajados, si el puerto esta cogido, las ultimas citas y avisos—
y se pega una vez.

No imprime IPs ni nombres de maquina: el informe se pega en sitios publicos.
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
    import conocimiento
    import frases
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
        citas = sorted(agenda.Agenda(n.ruta.name, n.horario).citas(),
                       key=lambda c: (c["fecha"], c["hora"]))[-5:]
        lineas.append(f"citas: {len(citas)} ultimas")
        lineas += [f"  {c['fecha']} {c['hora']} {c['servicio'] or '—'} · {c['nombre']}"
                   for c in citas]
    ultimos = avisos.listar(limite=5)
    lineas.append(f"avisos: {len(avisos.listar())} en total, ultimos:")
    lineas += [f"  [{a['tipo']}] {a['fecha']} {a['hora']} {a['texto'][:70]}" for a in ultimos]
    return lineas


def informe(negocio: str, puerto: int, corto: bool) -> str:
    en_venv = sys.prefix != sys.base_prefix
    lineas = [
        f"python {sys.version.split()[0]} · {'venv' if en_venv else 'SIN venv'}",
        f"faster-whisper {_version('faster-whisper')} · piper-tts {_version('piper-tts')} · "
        f"onnxruntime {_version('onnxruntime')} · ctranslate2 {_version('ctranslate2')}",
        *modelos(),
        f"puerto {puerto}: {'cogido (¿el servidor?)' if puerto_cogido(puerto) else 'libre'}",
    ]
    if corto:
        return "\n".join(lineas + negocio_y_datos(negocio)[:1])

    lineas += ["", *negocio_y_datos(negocio)]
    servicio = Path.home() / ".config" / "systemd" / "user" / "gjallarhorn.service"
    lineas += ["", f"servicio systemd: {'instalado' if servicio.exists() else 'no instalado (make arrancar)'}"]
    datos = os.environ.get("GJALLARHORN_DATOS")
    lineas.append(f"datos en: {datos or 'datos/ dentro del repo'}")
    return "\n".join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Que le pasa a esta maquina")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--puerto", type=int, default=8080)
    parser.add_argument("--corto", action="store_true")
    args = parser.parse_args()
    print(informe(args.negocio, args.puerto, args.corto))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
