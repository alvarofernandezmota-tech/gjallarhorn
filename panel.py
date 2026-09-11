"""El panel del dueño: abrir el móvil y ver cómo va el día.

Hasta aquí, quien lleva el negocio se enteraba de las cosas por Telegram
—avisos sueltos, según pasan— y por la terminal (`make estado`, `agenda.py`).
Eso vale para quien programa. Para quien tiene una peluquería, no: lo que
hace falta es **una pantalla** que conteste de un vistazo a «¿qué tengo hoy?».

Esto es esa pantalla, y es solo eso: mirar el día y quitar una cita. No se
reserva desde aquí —eso lo hace el teléfono, que es quien habla con el
cliente— ni se edita el conocimiento, que son ficheros de texto.

## Por qué aquí SÍ salen los nombres y los teléfonos

`diagnostico.py` no enseña ni un nombre, y es deliberado: eso se pega en un
chat, en un correo o en una incidencia, y lo que sale de casa no puede llevar
datos de clientes.

El panel es lo contrario: es **la libreta del dueño**, y una libreta sin
nombres no sirve para nada —hay que saber a quién llamar si se anula algo—.
Lo que hace que eso sea aceptable no es una promesa, son dos hechos:

1. Vive en el puerto privado (`servidor.Recepcion`), el que **no** se publica
   nunca. El puerto que sale a internet no tiene ni ruta para esto.
2. Se llega por `tailscale serve`, o sea, desde los dispositivos del dueño.

Si algún día esto se abre a internet, esta decisión hay que rehacerla entera,
no añadirle una contraseña por encima.

## El teléfono del cliente es una aproximación, y se dice

La agenda guarda el **nombre** que dio quien llamó; los teléfonos están en
`memoria.py`, por número. Aquí se cruzan por nombre, que es lo que hay, y por
eso el teléfono solo se enseña para poder llamar: nunca se manda nada solo.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import agenda as _agenda
import aprender
import avisos
import conocimiento
import fechas
import memoria

# Cuántos días se enseñan. Hoy y mañana es lo que se mira de verdad; la
# semana entera es una hoja de cálculo, y para eso ya está `agenda.py`.
DIAS = 2

# Cuántos avisos caben en la pantalla sin convertirla en un registro.
TOPE_AVISOS = 20

# Y cuántas cosas de las que no supo contestar. Es una lista para hacer algo
# con ella —escribir un párrafo—, no un informe.
TOPE_FALTAS = 6


@dataclass(frozen=True)
class Dia:
    """Un día del panel, ya masticado para pintarlo."""

    fecha: str
    dicho: str
    cerrado: bool
    citas: list[dict]
    huecos: list[str]
    previsto: float
    sin_precio: int

    def como_dict(self) -> dict:
        return {"fecha": self.fecha, "dicho": self.dicho, "cerrado": self.cerrado,
                "citas": self.citas, "huecos": self.huecos,
                "previsto": round(self.previsto, 2), "sin_precio": self.sin_precio}


def _precio_de(servicio: str | None, base: Path | None) -> tuple[str, float]:
    """(lo que pone la tabla, cuánto es en números). Sin tabla, cero.

    El número sale de la tabla del dueño, igual que por teléfono: aquí no se
    estima ni se redondea nada. Lo que no tiene precio escrito se cuenta
    aparte y se dice, en vez de sumar un cero disimulado.
    """
    if not servicio:
        return "", 0.0
    for fila in conocimiento.tarifas(base):
        if fila["servicio"] == servicio:
            escrito = fila.get("precio", "")
            numero = "".join(c for c in escrito.replace(",", ".")
                             if c.isdigit() or c == ".")
            try:
                return escrito, float(numero)
            except ValueError:
                return escrito, 0.0
    return "", 0.0


def _telefono_de(nombre: str | None, fichas: list) -> str:
    """El teléfono de quien se llama así, si se le conoce. Ver la cabecera."""
    buscado = fechas.sin_tildes(nombre or "").strip()
    if not buscado:
        return ""
    for ficha in fichas:
        if fechas.sin_tildes(ficha.nombre or "") == buscado:
            return ficha.telefono
    return ""


def dia(negocio, agenda, fecha: date, hoy: date, fichas: list) -> Dia:
    """Un día entero: sus citas, sus huecos y lo que se espera facturar."""
    iso = fecha.isoformat()
    citas, previsto, sin_precio = [], 0.0, 0
    for cita in sorted(agenda.citas(iso) if agenda else [], key=lambda c: c["hora"]):
        escrito, numero = _precio_de(cita.get("servicio"), negocio.conocimiento)
        previsto += numero
        sin_precio += 0 if numero else 1
        citas.append({
            "id": cita["id"],
            "hora": cita["hora"],
            "dicha": fechas.hora_en_palabras(cita["hora"]),
            "servicio": cita.get("servicio") or "",
            "nombre": cita.get("nombre") or "",
            "telefono": _telefono_de(cita.get("nombre"), fichas),
            "duracion": cita.get("duracion", 0),
            "precio": escrito,
        })

    cerrado = agenda is not None and agenda.horario is not None \
        and not agenda.horario.abre(fecha)
    libres = agenda.huecos(iso, _agenda.DURACION_POR_DEFECTO, tope=99) if agenda else []
    return Dia(fecha=iso, dicho=fechas.en_palabras(iso, hoy), cerrado=cerrado,
               citas=citas, huecos=[fechas.hora_en_palabras(h.hora) for h in libres],
               previsto=previsto, sin_precio=sin_precio)


def vista(negocio, ahora=None) -> dict:
    """Todo lo que pinta el panel, de una vez.

    Una sola consulta y un solo JSON: la página se refresca sola cada poco, y
    tres peticiones por refresco es pedirle a un servidor de un hilo que se
    entretenga mientras puede estar sonando el teléfono.
    """
    agenda = _agenda.Agenda(negocio.ruta.name, negocio.horario,
                            ahora=ahora) if negocio.horario else None
    reloj = (agenda.ahora() if agenda is not None else (ahora or fechas.ahora()))
    hoy = reloj.date()
    fichas = memoria.fichas()

    dias = [dia(negocio, agenda, hoy + timedelta(days=salto), hoy, fichas)
            for salto in range(DIAS)]
    pendientes = avisos.listar(solo_nuevos=True)
    ultimos = avisos.listar(limite=TOPE_AVISOS)    # ya vienen de lo nuevo a lo viejo
    # Lo que le preguntan y no sabe contestar. Aquí sí sale lo preguntado una
    # sola vez: el dueño está mirando la pantalla y decide él si le interesa.
    faltan = aprender.faltas(negocio.conocimiento, hoy=hoy)[:TOPE_FALTAS]

    return {
        "negocio": negocio.nombre,
        "ahora": reloj.strftime("%H:%M"),
        "fecha": hoy.isoformat(),
        "dias": [d.como_dict() for d in dias],
        "faltas": [f.como_dict() for f in faltan],
        "avisos": [{"id": a["id"], "tipo": a["tipo"], "hora": a.get("hora", ""),
                    "fecha": a.get("fecha", ""), "texto": a["texto"],
                    "visto": bool(a.get("visto"))} for a in ultimos],
        "cuentas": {
            "citas_hoy": len(dias[0].citas),
            "huecos_hoy": len(dias[0].huecos),
            "sin_ver": len(pendientes),
            "clientes": len(fichas),
            "faltas": len(faltan),
            "previsto_hoy": round(dias[0].previsto, 2),
        },
    }


def anular(negocio, id_cita: int, ahora=None) -> dict | None:
    """Quita una cita desde el panel. Devuelve la cita quitada, o None.

    Deja aviso, como todo lo que toca la agenda: el registro de llamadas es
    donde se mira qué pasó, y una cita que desaparece sin rastro es
    exactamente lo que no puede pasar aquí. El aviso dice que fue desde el
    panel, para distinguirlo de una anulación por teléfono.
    """
    if negocio.horario is None:
        return None
    agenda = _agenda.Agenda(negocio.ruta.name, negocio.horario, ahora=ahora)
    quitada = agenda.anular(id_cita)
    if quitada is None:
        return None
    avisos.registrar("cita", f"ANULADA desde el panel: {quitada.get('servicio') or 'cita'}, "
                             f"el {quitada['fecha']} a las {quitada['hora']}, "
                             f"a nombre de {quitada.get('nombre')}")
    if (telefono := _telefono_de(quitada.get("nombre"), memoria.fichas())):
        memoria.apuntar_anulacion(telefono)
    return quitada


def marcar_vistos(ids: list[int] | None = None) -> int:
    """Da por leídos unos avisos. Sin lista, todos."""
    return avisos.marcar_vistos(ids)


def main(argumentos: list[str] | None = None) -> int:
    """`python3 panel.py`: lo mismo que enseña la pantalla, en la terminal."""
    import argparse

    import negocio as negocios

    parser = argparse.ArgumentParser(description="El panel del dueño, en texto")
    parser.add_argument("--negocio", default="peluqueria")
    args = parser.parse_args(argumentos)

    try:
        datos = vista(negocios.cargar(args.negocio))
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return 1
    print(f"{datos['negocio']} · {datos['ahora']}")
    for jornada in datos["dias"]:
        cabeza = jornada["dicho"][0].upper() + jornada["dicho"][1:]
        if jornada["cerrado"]:
            print(f"\n{cabeza}: cerrado")
            continue
        print(f"\n{cabeza}: {len(jornada['citas'])} cita(s), "
              f"{len(jornada['huecos'])} hueco(s) libres"
              + (f", previsto {jornada['previsto']:.0f} €" if jornada["previsto"] else ""))
        for cita in jornada["citas"]:
            print(f"   {cita['hora']}  {cita['servicio'] or '—':22} {cita['nombre']}"
                  + (f"  {cita['telefono']}" if cita["telefono"] else ""))
    sin_ver = [a for a in datos["avisos"] if not a["visto"]]
    print(f"\n{len(sin_ver)} aviso(s) sin ver")
    for aviso in sin_ver[:5]:
        print(f"   [{aviso['tipo']}] {aviso['texto'][:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
