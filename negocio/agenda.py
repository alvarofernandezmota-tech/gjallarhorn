"""La agenda: qué huecos hay y cuáles están cogidos. Lo que faltaba de verdad.

Sin esto el recepcionista «toma nota» y promete que alguien confirmará. Con
esto **reserva**: comprueba que el negocio abre ese día, que la hora cae
dentro del horario y que nadie tiene ya ese hueco. Y si no cabe, propone los
huecos que sí hay, en vez de mandar a alguien a una puerta cerrada.

## El horario vive en `negocio.toml`

    [horario]
    lunes = []                              # cerrado
    martes = ["10:00-14:00", "16:30-20:00"]
    sabado = ["09:00-14:00"]

Sin `[horario]` no hay agenda: se toma nota como hasta ahora. Es a propósito:
antes que reservar contra un horario que nadie ha escrito, mejor no reservar.

## Lo que se guarda

Un JSON por negocio, `datos/agenda/<negocio>.json`, con `almacen.py`:
escritura atómica y versión de esquema. Cada cita lleva fecha, hora de inicio,
duración, servicio y nombre. Se **solapa** cuando dos citas se pisan en
minutos, no cuando empiezan a la misma hora: un tinte de 90 min a las 10
ocupa hasta las 11:30, y un corte a las 11 no cabe.
"""

import re
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from hugin.guardado import almacen
from hugin.guardado import datos
from hugin.mente import fechas

ESQUEMA = 1
VARIABLE = "GJALLARHORN_DATOS"

# El servidor atiende varias llamadas a la vez. Reservar y anular son
# leer-modificar-escribir sobre el mismo fichero: sin esto, dos llamadas
# simultaneas pueden pasar las dos la comprobacion de hueco y pisarse la
# escritura, y una de las dos citas desaparece sin que nadie se entere.
# `almacen` garantiza que el fichero quede entero, no que no se pise.
_ESCRIBIENDO = threading.Lock()

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
TRAMO = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")

# Si el servicio no dice cuánto dura, se reserva esto. Mejor pasarse que
# meter a dos personas en el mismo sillón.
DURACION_POR_DEFECTO = 30
# Las citas se ofrecen en múltiplos de esto.
PASO = 30


def _minutos(hora: str) -> int:
    h, m = hora.split(":")
    return int(h) * 60 + int(m)


def _hora(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def duracion_en_minutos(texto: str | None) -> int:
    """«90 min», «1 h», «1h30» → minutos. Sin nada reconocible, el defecto."""
    if not texto:
        return DURACION_POR_DEFECTO
    t = texto.lower().replace(",", ".")
    if m := re.search(r"(\d+)\s*h(?:oras?)?\s*(?:y\s*)?(\d+)?", t):
        return int(m.group(1)) * 60 + int(m.group(2) or 0)
    if m := re.search(r"(\d+(?:\.\d+)?)\s*(?:min|m\b)", t):
        return int(float(m.group(1)))
    if m := re.search(r"(\d+)", t):
        return int(m.group(1))
    return DURACION_POR_DEFECTO


@dataclass(frozen=True)
class Horario:
    """Los tramos de apertura de cada día, en minutos desde medianoche."""

    tramos: dict[int, list[tuple[int, int]]]   # weekday → [(inicio, fin)]

    @classmethod
    def desde(cls, config: dict | None) -> "Horario | None":
        """Del `[horario]` de negocio.toml. None si no hay horario escrito."""
        if not config:
            return None
        tramos: dict[int, list[tuple[int, int]]] = {}
        for nombre, lista in config.items():
            clave = fechas.sin_tildes(nombre)
            if clave not in DIAS:
                raise ValueError(f"[horario]: «{nombre}» no es un día. Valen: {', '.join(DIAS)}")
            dia = []
            for tramo in lista or []:
                m = TRAMO.match(str(tramo))
                if not m:
                    raise ValueError(f"[horario] {nombre}: «{tramo}» no es un tramo HH:MM-HH:MM")
                # Un reloj tiene 24 horas y 60 minutos. «25:00» encajaba en el
                # patrón y se guardaba como 1500 minutos: un tramo al que no
                # llega ningún día, o sea, un negocio que nunca abre y nadie
                # sabe por qué.
                for hora, minutos in ((m.group(1), m.group(2)), (m.group(3), m.group(4))):
                    if int(hora) > 23 or int(minutos) > 59:
                        raise ValueError(
                            f"[horario] {nombre}: «{tramo}» no es una hora "
                            f"(las horas van de 00 a 23 y los minutos de 00 a 59)")
                ini = int(m.group(1)) * 60 + int(m.group(2))
                fin = int(m.group(3)) * 60 + int(m.group(4))
                if fin <= ini:
                    raise ValueError(f"[horario] {nombre}: «{tramo}» acaba antes de empezar")
                dia.append((ini, fin))
            tramos[DIAS.index(clave)] = sorted(dia)
        return cls(tramos)

    def abre(self, dia: date) -> bool:
        return bool(self.tramos.get(dia.weekday()))

    def tramo_de(self, dia: date, minutos: int) -> tuple[int, int] | None:
        """El tramo en el que cae ese minuto, o None si está cerrado."""
        for ini, fin in self.tramos.get(dia.weekday(), []):
            if ini <= minutos < fin:
                return (ini, fin)
        return None

    def proxima_apertura(self, dia: date, minutos: int, dias: int = 8) -> tuple[date, int] | None:
        """Cuándo vuelve a abrir a partir de ese momento: (día, minuto).

        Hace falta para contestar «ahora está cerrado, abrimos el martes a
        las diez» en vez de soltar el horario entero y que quien llama lo
        traduzca. None si no abre en toda la semana que viene.
        """
        for salto in range(dias):
            cuando = dia + timedelta(days=salto)
            for ini, _ in self.tramos.get(cuando.weekday(), []):
                if salto > 0 or ini > minutos:
                    return (cuando, ini)
        return None

    def cabe(self, dia: date, inicio: int, duracion: int) -> bool:
        """¿Un servicio que empieza a `inicio` y dura `duracion` cae entero dentro?"""
        return any(ini <= inicio and inicio + duracion <= fin
                   for ini, fin in self.tramos.get(dia.weekday(), []))


@dataclass(frozen=True)
class Hueco:
    fecha: str
    hora: str

    @property
    def dicho(self) -> str:
        return f"{fechas.en_palabras(self.fecha)} a {fechas.hora_en_palabras(self.hora)}"


class Agenda:
    """Las citas de un negocio. Lee y escribe con `almacen`, nunca a pelo."""

    def __init__(self, negocio: str, horario: Horario | None, ruta: Path | None = None,
                 ahora=None):
        self.negocio = negocio
        self.horario = horario
        self.ruta = ruta or _ruta(negocio)
        self._ahora = ahora        # para las pruebas; si no, el reloj de Madrid

    def ahora(self) -> datetime:
        return self._ahora or fechas.ahora()

    # -- almacenamiento ------------------------------------------------------

    def citas(self, fecha: str | None = None) -> list[dict]:
        todas = almacen.cargar(self.ruta, ESQUEMA, vacio=[])
        return [c for c in todas if fecha is None or c["fecha"] == fecha]

    def _guardar(self, citas: list[dict]) -> None:
        almacen.guardar(self.ruta, citas, ESQUEMA)

    # -- consulta ------------------------------------------------------------

    def _ocupado(self, fecha: str, inicio: int, duracion: int) -> dict | None:
        """La cita con la que se solapa, o None. Solapar es pisarse en minutos."""
        fin = inicio + duracion
        for cita in self.citas(fecha):
            ini_c = _minutos(cita["hora"])
            fin_c = ini_c + cita["duracion"]
            if inicio < fin_c and ini_c < fin:
                return cita
        return None

    def _ya_paso(self, fecha: str, hora: str) -> bool:
        """¿Esa fecha y hora quedan por detras del reloj?

        Sin esto, quien llama a las once y dice «a las diez» se va con una
        cita a una hora que ya paso: nadie la atiende y el hueco queda
        ocupado. Se descubrio probando el cambio de cita.
        """
        ahora = self.ahora()
        dia = date.fromisoformat(fecha)
        if dia < ahora.date():
            return True
        return dia == ahora.date() and _minutos(hora) <= ahora.hour * 60 + ahora.minute

    def por_que_no(self, fecha: str, hora: str, duracion: int) -> str | None:
        """None si cabe; si no, el motivo en una palabra.

        pasado | cerrado | fuera | ocupado. El orden importa: «ya ha pasado»
        explica mejor que «esta ocupado» una hora de esta manana.
        """
        if self.horario is None:
            return None
        if self._ya_paso(fecha, hora):
            return "pasado"
        dia = date.fromisoformat(fecha)
        if not self.horario.abre(dia):
            return "cerrado"
        inicio = _minutos(hora)
        if not self.horario.cabe(dia, inicio, duracion):
            return "fuera"
        if self._ocupado(fecha, inicio, duracion):
            return "ocupado"
        return None

    def huecos(self, fecha: str, duracion: int, desde: int | None = None,
               tope: int = 3, hasta: int | None = None) -> list[Hueco]:
        """Los primeros huecos libres de un día en los que cabe `duracion`.

        `desde` y `hasta` en minutos del día: «por la tarde» son los huecos
        desde las 14:00; «por la mañana», los que acaban antes.
        """
        if self.horario is None:
            return []
        dia = date.fromisoformat(fecha)
        # Un hueco que ya paso no es un hueco. Hoy se empieza a contar desde
        # el reloj, no desde que abre el negocio.
        ahora = self.ahora()
        if dia < ahora.date():
            return []
        if dia == ahora.date():
            # El minuto que corre ya ha pasado para `_ya_paso`, que usa <=.
            # Sin el +1, `huecos()` ofrecía el hueco de las 10:30 a las 10:30
            # en punto y `reservar()` lo rechazaba por «pasado»: un hueco
            # ofrecido que no se puede coger es peor que no ofrecerlo.
            minimo = ahora.hour * 60 + ahora.minute + 1
            desde = max(desde, minimo) if desde is not None else minimo
        encontrados = []
        for ini, fin in self.horario.tramos.get(dia.weekday(), []):
            inicio = ini
            while inicio + duracion <= fin:
                if (desde is None or inicio >= desde) \
                        and (hasta is None or inicio + duracion <= hasta) \
                        and not self._ocupado(fecha, inicio, duracion):
                    encontrados.append(Hueco(fecha, _hora(inicio)))
                    if len(encontrados) >= tope:
                        return encontrados
                inicio += PASO
        return encontrados

    def proximos_huecos(self, desde: str, duracion: int, dias: int = 14,
                        tope: int = 3, por_dia: int | None = None) -> list[Hueco]:
        """Los primeros huecos a partir de un día, mirando hasta `dias` adelante.

        `por_dia=1` da el primer hueco de cada día: para decir «el martes, el
        miércoles o el jueves» en vez de tres horas del mismo martes.
        """
        encontrados: list[Hueco] = []
        dia = date.fromisoformat(desde)
        for _ in range(dias):
            cupo = min(tope - len(encontrados), por_dia or tope)
            encontrados += self.huecos(dia.isoformat(), duracion, tope=cupo)
            if len(encontrados) >= tope:
                break
            dia += timedelta(days=1)
        return encontrados[:tope]

    def citas_de(self, nombre: str, desde: str | None = None) -> list[dict]:
        """Las citas de alguien de hoy en adelante, la mas proxima primero.

        Se busca por nombre sin tildes ni mayusculas: quien llama dice «Alvaro»
        y Whisper escribe «Álvaro» o al reves, y eso no puede hacer que una
        cita no aparezca.
        """
        buscado = fechas.sin_tildes(nombre or "").strip()
        if not buscado:
            return []
        desde = desde or self.ahora().strftime("%Y-%m-%d")
        suyas = [c for c in self.citas()
                 if fechas.sin_tildes(c.get("nombre") or "") == buscado
                 and c["fecha"] >= desde]
        return sorted(suyas, key=lambda c: (c["fecha"], c["hora"]))

    def anular(self, id_cita: int) -> dict | None:
        """Quita la cita y la devuelve. None si ya no estaba.

        Libera el hueco de verdad: lo que se anula se borra, no se marca. Una
        cita anulada que sigue ocupando sitio es peor que no anularla, porque
        nadie lo sabe.
        """
        with _ESCRIBIENDO:
            citas = self.citas()
            quitada = next((c for c in citas if c["id"] == id_cita), None)
            if quitada is None:
                return None
            self._guardar([c for c in citas if c["id"] != id_cita])
            return quitada

    def renombrar(self, id_cita: int, nombre: str) -> dict | None:
        """Cambia el nombre de una cita ya reservada. None si ya no está.

        «A nombre de Lucía», dicho **después** de reservar, es una corrección,
        no otra cita. Sin esto se apuntaba la reserva al que llamaba y la
        que venía a cortarse el pelo no aparecía en ningún sitio.
        """
        with _ESCRIBIENDO:
            citas = self.citas()
            for cita in citas:
                if cita["id"] == id_cita:
                    cita["nombre"] = nombre
                    self._guardar(citas)
                    return cita
            return None

    # -- reserva -------------------------------------------------------------

    def reservar(self, fecha: str, hora: str, duracion: int, servicio: str | None,
                 nombre: str, ahora: datetime | None = None) -> dict:
        """Apunta la cita. Levanta ValueError con el motivo si no cabe.

        Se vuelve a comprobar aquí aunque ya se haya preguntado antes: entre
        la pregunta y la reserva puede haber entrado otra llamada.
        """
        with _ESCRIBIENDO:
            return self._reservar(fecha, hora, duracion, servicio, nombre, ahora)

    def _reservar(self, fecha, hora, duracion, servicio, nombre, ahora) -> dict:
        if (motivo := self.por_que_no(fecha, hora, duracion)) is not None:
            raise ValueError(motivo)
        citas = self.citas()
        cita = {
            "id": max((c["id"] for c in citas), default=0) + 1,
            "fecha": fecha, "hora": hora, "duracion": duracion,
            "servicio": servicio, "nombre": nombre,
            "creada": (ahora or fechas.ahora()).strftime("%Y-%m-%d %H:%M"),
        }
        citas.append(cita)
        self._guardar(citas)
        return cita


def _ruta(negocio: str) -> Path:
    """Las citas de un negocio, en su carpeta. Ver `datos.py`."""
    return datos.carpeta_de(negocio) / "agenda.json"


def main() -> int:
    """`python3 agenda.py --negocio peluqueria [--dia 2026-09-17]`: las citas."""
    import argparse

    from hugin.negocio import negocio as negocios

    parser = argparse.ArgumentParser(description="Las citas de un negocio")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--dia", help="solo ese día (AAAA-MM-DD)")
    args = parser.parse_args()

    n = negocios.cargar(args.negocio)
    agenda = Agenda(n.ruta.name, n.horario)
    citas = sorted(agenda.citas(args.dia), key=lambda c: (c["fecha"], c["hora"]))
    if not citas:
        print("Sin citas.")
        return 0
    for c in citas:
        print(f"{c['fecha']} {c['hora']}  {c['duracion']:>3} min  "
              f"{c['servicio'] or '—':<22} {c['nombre']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
