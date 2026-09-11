"""Lo que el negocio recuerda de quien llama. Y lo que no.

El teléfono ya sabía dos cosas —el nombre y cuántas veces había llamado— y
con eso saludaba por el nombre. Aquí eso se convierte en una ficha: lo que
suele pedir, a qué hora suele venir, cuántas veces ha anulado y cuándo fue la
última. Es la diferencia entre un contestador y el sitio donde te conocen:

    — Peluquería, dígame.        Hola, Marta. ¿Le apunto lo de siempre?
    — Sí, un tinte.              Perfecto. ¿El jueves por la tarde, como siempre?

## Esto son datos personales, así que hay reglas

No es un detalle legal para mirar a otro lado: es el teléfono de alguien y lo
que se hace con su pelo. Tres cosas, escritas en el código y no en un aviso:

1. **Solo lo que sirve para atender la llamada.** El nombre, el servicio, la
   franja y las cuentas. Ni lo que dijo, ni transcripciones, ni nada libre
   que no haya escrito el dueño a propósito en una nota.
2. **Se olvida solo.** `caducar()` borra las fichas que llevan
   `CADUCA_DIAS` sin llamar. Sin eso, un fichero de clientes crece para
   siempre y nadie lo mira hasta que hay un problema.
3. **Se puede borrar de verdad.** `olvidar(telefono)` quita la ficha entera,
   y `make olvidar TELEFONO=...` lo hace desde fuera. Si alguien lo pide por
   teléfono, el dueño tiene que poder hacerlo en diez segundos.

Y una que ya estaba en `diagnostico.py` y aquí se mantiene: **nada de esto
sale en un informe**. Los informes llevan cuentas, no nombres.

## De dónde salen los datos

De lo que ya pasa en la llamada, no de preguntar más:

    entrada → apuntar_llamada(numero)
    reserva → apuntar_cita(numero, servicio, fecha, hora)
    anular  → apuntar_anulacion(numero)

`telefonia.py` los llama en los mismos sitios donde antes escribía
`clientes.json`, y ese fichero se lee igual: la ficha vieja se entiende y se
completa sola.

## Lo que NO hace

No decide nada. No dice «a este le subo el precio» ni «a este no le cojo la
cita». Da datos, y quien los usa es `recepcion.py` para dos cosas concretas:
sugerir lo de siempre y proponer la franja de siempre. Las dos se pueden
quitar sin que se caiga nada.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import almacen
import datos
import fechas

ESQUEMA = 2
VARIABLE = "GJALLARHORN_DATOS"

# Cuánto se guarda una ficha sin volver a llamar. Dos años es una clientela de
# peluquería con margen: quien no ha vuelto en dos años ya no es un cliente al
# que se le reconoce la voz, es un dato de sobra.
CADUCA_DIAS = 730

# Cuántas veces hay que pedir lo mismo para que sea «lo de siempre». Con una
# no: que alguien se tiñera una vez no convierte el tinte en su costumbre.
PARA_SER_COSTUMBRE = 2

_ESCRIBIENDO = __import__("threading").Lock()


@dataclass
class Ficha:
    """Lo que se sabe de un teléfono. Todo contable, nada libre."""

    telefono: str
    nombre: str | None = None
    llamadas: int = 0
    citas: int = 0
    anuladas: int = 0
    primera: str | None = None
    ultima: str | None = None
    servicios: dict[str, int] = field(default_factory=dict)
    franjas: dict[str, int] = field(default_factory=dict)
    notas: list[str] = field(default_factory=list)

    @property
    def habitual(self) -> str | None:
        """El servicio que pide siempre, si es que hay uno."""
        if not self.servicios:
            return None
        servicio, veces = max(self.servicios.items(), key=lambda s: (s[1], s[0]))
        return servicio if veces >= PARA_SER_COSTUMBRE else None

    @property
    def franja(self) -> str | None:
        """La franja a la que suele venir: «manana» o «tarde»."""
        if not self.franjas:
            return None
        franja, veces = max(self.franjas.items(), key=lambda f: (f[1], f[0]))
        return franja if veces >= PARA_SER_COSTUMBRE else None

    @property
    def conocido(self) -> bool:
        """¿Se le puede saludar por su nombre?"""
        return bool(self.nombre)

    def resumen(self) -> str:
        """Una línea para quien lleva el negocio. Para el dueño, no para el cliente."""
        partes = [self.nombre or "sin nombre",
                  f"{self.llamadas} llamada{'s' if self.llamadas != 1 else ''}"]
        if self.citas:
            partes.append(f"{self.citas} cita{'s' if self.citas != 1 else ''}")
        if self.anuladas:
            partes.append(f"{self.anuladas} anulada{'s' if self.anuladas != 1 else ''}")
        if self.habitual:
            partes.append(f"suele pedir {self.habitual.lower()}")
        if self.franja:
            partes.append(f"suele venir por la {self.franja.replace('manana', 'mañana')}")
        if self.ultima:
            partes.append(f"última {self.ultima}")
        return " · ".join(partes)

    def como_dict(self) -> dict:
        return {"nombre": self.nombre, "llamadas": self.llamadas, "citas": self.citas,
                "anuladas": self.anuladas, "primera": self.primera, "ultima": self.ultima,
                "servicios": self.servicios, "franjas": self.franjas, "notas": self.notas}

    @classmethod
    def desde(cls, telefono: str, datos: dict) -> "Ficha":
        """Una ficha desde el disco. Entiende también el formato viejo.

        El `clientes.json` de antes tenía `nombre`, `llamadas` y `ultima`. Se
        lee tal cual y lo que falta se queda a cero: nadie pierde su nombre
        por cambiar de formato.
        """
        return cls(
            telefono=telefono,
            nombre=datos.get("nombre") or None,
            llamadas=int(datos.get("llamadas") or 0),
            citas=int(datos.get("citas") or 0),
            anuladas=int(datos.get("anuladas") or 0),
            primera=datos.get("primera") or datos.get("ultima"),
            ultima=datos.get("ultima"),
            servicios=dict(datos.get("servicios") or {}),
            franjas=dict(datos.get("franjas") or {}),
            notas=list(datos.get("notas") or []),
        )


def ruta() -> Path:
    """El fichero de clientes **de este negocio**. Ver `datos.py`."""
    return datos.fichero("clientes.json")


def _todas() -> dict:
    """El fichero entero. Acepta el esquema viejo sin quejarse.

    `almacen.cargar` levanta si la versión no es la que se le pide, y eso es
    lo correcto para un formato que cambia de verdad. Aquí no cambia: la
    ficha vieja es una ficha nueva con campos a cero, así que se prueba la
    versión de ahora y, si no, la de antes.
    """
    for version in (ESQUEMA, 1):
        try:
            return almacen.cargar(ruta(), version, vacio={})
        except ValueError:
            continue
    return {}


def _guardar(todas: dict) -> None:
    almacen.guardar(ruta(), todas, ESQUEMA)


def ficha(telefono: str) -> Ficha | None:
    """Lo que se sabe de ese teléfono, o None si es la primera vez."""
    if not telefono:
        return None
    datos = _todas().get(telefono)
    return Ficha.desde(telefono, datos) if datos else None


def fichas() -> list[Ficha]:
    """Todas las fichas. Para los agentes y para el informe del dueño."""
    return [Ficha.desde(telefono, datos) for telefono, datos in sorted(_todas().items())]


def _actualizar(telefono: str, cambiar) -> Ficha | None:
    """Lee, cambia y guarda, con el fichero cerrado a otros mientras tanto."""
    if not telefono:
        return None
    with _ESCRIBIENDO:
        todas = _todas()
        actual = Ficha.desde(telefono, todas.get(telefono, {}))
        cambiar(actual)
        actual.ultima = fechas.hoy()
        actual.primera = actual.primera or actual.ultima
        todas[telefono] = actual.como_dict()
        _guardar(todas)
        return actual


def apuntar_llamada(telefono: str, nombre: str | None = None) -> Ficha | None:
    """Una llamada más, y el nombre si lo ha dado.

    El nombre que ya había NO se pisa con un vacío: que en una llamada no
    diga cómo se llama no borra que en la anterior lo dijera.
    """
    def cambiar(f: Ficha) -> None:
        f.llamadas += 1
        f.nombre = nombre or f.nombre
    return _actualizar(telefono, cambiar)


def apuntar_cita(telefono: str, servicio: str | None, hora: str | None = None) -> Ficha | None:
    """Una cita cerrada: cuenta, y con qué servicio y a qué franja."""
    def cambiar(f: Ficha) -> None:
        f.citas += 1
        if servicio:
            f.servicios[servicio] = f.servicios.get(servicio, 0) + 1
        if (cual := franja_de(hora)) is not None:
            f.franjas[cual] = f.franjas.get(cual, 0) + 1
    return _actualizar(telefono, cambiar)


def apuntar_anulacion(telefono: str) -> Ficha | None:
    """Una cita anulada. Se cuenta, no se juzga: el dueño lo verá y decidirá."""
    def cambiar(f: Ficha) -> None:
        f.anuladas += 1
    return _actualizar(telefono, cambiar)


def apuntar_nota(telefono: str, nota: str) -> Ficha | None:
    """Una nota del dueño sobre este cliente. La escribe él, no la llamada."""
    def cambiar(f: Ficha) -> None:
        f.notas.append(nota.strip())
    return _actualizar(telefono, cambiar)


def franja_de(hora: str | None) -> str | None:
    """«17:00» → «tarde». None si no hay hora."""
    try:
        h = int(str(hora).split(":")[0])
    except (AttributeError, ValueError, IndexError):
        return None
    return "manana" if h < 14 else "tarde"


def olvidar(telefono: str) -> bool:
    """Borra la ficha entera. True si había algo que borrar.

    El derecho al olvido no es un `borrado = true`: si alguien lo pide, sus
    datos dejan de estar. Sus citas futuras siguen en la agenda, que son del
    negocio y las necesita para atenderle el día que venga.
    """
    with _ESCRIBIENDO:
        todas = _todas()
        if telefono not in todas:
            return False
        del todas[telefono]
        _guardar(todas)
        return True


def caducar(dias: int = CADUCA_DIAS, hoy: date | None = None) -> list[str]:
    """Borra las fichas que llevan `dias` sin llamar. Devuelve cuáles.

    Se llama desde los agentes, una vez al día. Guardar para siempre el
    teléfono de alguien que llamó una vez en 2019 no ayuda a atenderle: es
    tener datos de más, que es justo lo que no se quiere tener.
    """
    limite = (hoy or fechas.ahora().date()) - timedelta(days=dias)
    with _ESCRIBIENDO:
        todas = _todas()
        caducadas = []
        for telefono, datos in list(todas.items()):
            ultima = datos.get("ultima")
            try:
                cuando = datetime.strptime(ultima, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                continue        # sin fecha no se borra: se deja y se ve en el informe
            if cuando < limite:
                caducadas.append(telefono)
                del todas[telefono]
        if caducadas:
            _guardar(todas)
        return caducadas


def cuentas() -> dict:
    """Números para el informe del dueño. **Sin un solo nombre ni teléfono.**"""
    todas = fichas()
    return {
        "fichas": len(todas),
        "con_nombre": sum(1 for f in todas if f.conocido),
        "repiten": sum(1 for f in todas if f.llamadas > 1),
        "con_costumbre": sum(1 for f in todas if f.habitual),
    }


def main() -> int:
    """`python3 memoria.py`: las fichas, o `--olvidar <telefono>`."""
    import argparse

    parser = argparse.ArgumentParser(description="Lo que el negocio recuerda de quien llama")
    parser.add_argument("--olvidar", metavar="TELEFONO", help="borrar la ficha de un número")
    parser.add_argument("--caducar", action="store_true",
                        help=f"borrar las fichas con más de {CADUCA_DIAS} días sin llamar")
    args = parser.parse_args()

    if args.olvidar:
        if olvidar(args.olvidar):
            print("🗑️  Olvidado. De ese número ya no se sabe nada.")
        else:
            print("No había ninguna ficha de ese número.")
        return 0

    if args.caducar:
        borradas = caducar()
        print(f"🗑️  {len(borradas)} ficha(s) caducada(s) y borrada(s).")
        return 0

    todas = fichas()
    if not todas:
        print("Todavía no ha llamado nadie.")
        return 0
    for f in todas:
        print(f"{f.telefono:16} {f.resumen()}")
    print(f"\n{len(todas)} ficha(s). `--olvidar <telefono>` borra una entera.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
