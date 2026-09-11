"""Lo que trabaja cuando no suena el teléfono.

El recepcionista atiende llamadas. Pero un negocio tiene cosas que pasan
entre llamada y llamada, y que hoy no hace nadie: recordar las citas de
mañana, ver qué huecos se han quedado sueltos, avisar de que un cliente lleva
medio año sin venir, o de que la tabla de precios tiene una fila torcida.

Eso es esto: **agentes que corren una vez al día** y dejan avisos. No hablan
con nadie, no llaman por teléfono y no deciden nada: ponen delante del dueño
lo que hay, con nombres y números, para que decida él.

## Todos tienen la misma forma

    def agente(mundo) -> Resultado | None

`mundo` es lo que necesitan —el negocio, la agenda, las fichas y el reloj— y
devuelven un `Resultado` o `None` si no hay nada que contar. Esa forma no es
capricho: **son funciones puras**, así que se prueban con una agenda de
mentira y un reloj fijo, sin tocar nada y sin esperar a que sea martes.

Quien escribe —registrar avisos, mandarlos al móvil— es `correr()`, en un
solo sitio. Un agente que escriba por su cuenta es un agente que no se puede
probar.

## Y ninguno manda nada al cliente

`recordatorios` deja **preparado** el mensaje de cada cita de mañana, pero no
lo manda: mandar SMS a clientes es otra decisión (y otra factura) y no se
toma por inercia desde aquí. El dueño lo ve en su móvil y lo manda si quiere.

## Cuándo corren

`make agentes` los corre a mano, y `make agentes-diarios` deja un timer de
systemd que los corre cada mañana. No corren dentro de la llamada: lo que
tarde un agente no puede hacerle esperar a quien está al teléfono.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import agenda as _agenda
import avisos
import conocimiento
import fechas
import frases as _frases
import memoria

# A partir de cuántos días sin aparecer se considera que un cliente se ha
# perdido. Seis meses en una peluquería es de sobra: quien se corta cada mes
# y lleva seis sin venir, no está viniendo.
PERDIDO_DIAS = 180

# Cuántos días mira el agente de huecos. Más de una semana no sirve de nada:
# los huecos de dentro de tres semanas se llenan solos.
HUECOS_DIAS = 7


@dataclass(frozen=True)
class Resultado:
    """Lo que un agente ha encontrado. Texto para el dueño, nada más."""

    agente: str
    titulo: str
    lineas: list[str] = field(default_factory=list)
    tipo: str = "cita"        # con qué tipo se registra el aviso

    def texto(self) -> str:
        return "\n".join([self.titulo, *(f"  {linea}" for linea in self.lineas)])


@dataclass
class Mundo:
    """Lo que ven los agentes. Se les da hecho para poder probarlos."""

    negocio: object
    agenda: _agenda.Agenda | None
    ahora: datetime
    fichas: list = field(default_factory=list)

    @property
    def hoy(self) -> date:
        return self.ahora.date()

    def citas_de(self, dia: date) -> list[dict]:
        if self.agenda is None:
            return []
        return sorted(self.agenda.citas(dia.isoformat()), key=lambda c: c["hora"])

    def ficha_de(self, nombre: str):
        """La ficha de quien se llama así, si se le conoce.

        Por nombre y no por teléfono porque la agenda guarda el nombre: es
        una aproximación, y por eso solo se usa para **sugerir** a quién
        avisar, nunca para mandarle nada.
        """
        buscado = fechas.sin_tildes(nombre or "").strip()
        if not buscado:
            return None
        for ficha in self.fichas:
            if fechas.sin_tildes(ficha.nombre or "") == buscado:
                return ficha
        return None


# ---- los agentes ---------------------------------------------------------

def recordatorios(mundo: Mundo) -> Resultado | None:
    """Las citas de mañana, con el mensaje listo para mandar a cada una.

    El agujero más caro de una peluquería son los que no aparecen. Un aviso
    la víspera es lo que lo tapa, y hoy no lo hace nadie porque nadie mira la
    agenda a las ocho de la tarde.
    """
    manana = mundo.hoy + timedelta(days=1)
    citas = mundo.citas_de(manana)
    if not citas:
        return None
    dicha = fechas.en_palabras(manana.isoformat(), mundo.hoy)
    lineas = []
    for cita in citas:
        hora = fechas.hora_en_palabras(cita["hora"])
        servicio = (cita.get("servicio") or "cita").lower()
        lineas.append(f"{cita['hora']} {cita.get('nombre') or '(sin nombre)'} — {servicio}")
        lineas.append(f'    para mandarle: "Hola, {cita.get("nombre") or ""}. Le recordamos '
                      f'su cita de {servicio} {dicha} a {hora}. {mundo.negocio.nombre}."')
    return Resultado("recordatorios",
                     f"{len(citas)} cita(s) {dicha}. Recuérdaselas hoy:", lineas)


def resumen(mundo: Mundo) -> Resultado | None:
    """Cómo viene el día: citas, huecos y lo que se espera facturar."""
    citas = mundo.citas_de(mundo.hoy)
    tarifas = {s["servicio"]: s.get("precio", "") for s in
               conocimiento.tarifas(mundo.negocio.conocimiento)}
    if not citas and mundo.agenda is None:
        return None

    previsto, sin_precio = 0.0, 0
    for cita in citas:
        precio = tarifas.get(cita.get("servicio") or "", "")
        numero = "".join(c for c in precio.replace(",", ".") if c.isdigit() or c == ".")
        try:
            previsto += float(numero)
        except ValueError:
            sin_precio += 1

    lineas = [f"{len(citas)} cita(s) hoy"]
    if citas:
        lineas.append(f"de {fechas.hora_en_palabras(citas[0]['hora'])} "
                      f"a {fechas.hora_en_palabras(citas[-1]['hora'])}")
    if previsto:
        lineas.append(f"previsto: {previsto:.0f} €"
                      + (f" (y {sin_precio} sin precio en la tabla)" if sin_precio else ""))
    if mundo.agenda is not None:
        libres = mundo.agenda.huecos(mundo.hoy.isoformat(), _agenda.DURACION_POR_DEFECTO, tope=99)
        lineas.append(f"{len(libres)} hueco(s) todavía libres hoy")
    pendientes = [a for a in avisos.listar() if not a.get("visto")]
    if pendientes:
        lineas.append(f"{len(pendientes)} aviso(s) sin ver")
    return Resultado("resumen", f"El día {mundo.hoy.isoformat()}:", lineas, tipo="llamada")


def huecos(mundo: Mundo) -> Resultado | None:
    """Los huecos de esta semana, y a quién se le podrían ofrecer.

    No los manda: dice cuáles son y qué clientes suelen venir a esa franja,
    que es lo que haría falta para llamarles. Decidir a quién se llama no es
    cosa de un programa.
    """
    if mundo.agenda is None:
        return None
    dias = [mundo.hoy + timedelta(days=salto) for salto in range(HUECOS_DIAS)]
    # Un negocio sin ninguna cita esta semana no tiene «días flojos»: está
    # empezando, o es agosto. Avisar de eso cada mañana es ruido.
    if not any(mundo.citas_de(dia) for dia in dias):
        return None

    por_dia = {dia.isoformat(): len(mundo.agenda.huecos(
        dia.isoformat(), _agenda.DURACION_POR_DEFECTO, tope=99)) for dia in dias}
    flojos = [fecha for fecha, cuantos in sorted(por_dia.items()) if cuantos >= 4][:5]
    if not flojos:
        return None

    lineas = [f"{fechas.en_palabras(fecha, mundo.hoy)}: {por_dia[fecha]} huecos libres"
              for fecha in flojos]
    habituales = [f.nombre for f in mundo.fichas if f.nombre and f.citas >= 2][:5]
    if habituales:
        lineas.append("clientes que repiten, por si quieres ofrecérselo: "
                      + ", ".join(habituales))
    return Resultado("huecos", "Días flojos esta semana:", lineas, tipo="llamada")


def seguimiento(mundo: Mundo) -> Resultado | None:
    """Quién lleva medio año sin aparecer, teniendo costumbre de venir."""
    limite = (mundo.hoy - timedelta(days=PERDIDO_DIAS)).isoformat()
    perdidos = [f for f in mundo.fichas
                if f.citas >= 2 and f.ultima and f.ultima < limite]
    if not perdidos:
        return None
    lineas = [f"{f.nombre or f.telefono} — {f.resumen()}" for f in perdidos[:10]]
    if len(perdidos) > 10:
        lineas.append(f"…y {len(perdidos) - 10} más")
    return Resultado("seguimiento",
                     f"{len(perdidos)} cliente(s) habituales que no vienen desde hace "
                     f"más de {PERDIDO_DIAS // 30} meses:", lineas, tipo="llamada")


def revision(mundo: Mundo) -> Resultado | None:
    """Lo que está mal y nadie ha mirado: la revisión del propio negocio.

    Esto es lo que, sin agente, se descubre el día que un cliente pregunta
    algo y el agente contesta mal. Aquí sale una vez al día y por escrito.
    """
    base = mundo.negocio.conocimiento
    problemas = []

    faltan = conocimiento.que_falta(base)
    if faltan:
        problemas.append(f"sin rellenar: {', '.join(faltan)}")
    problemas += [f"frases.toml: {p}" for p in _frases.problemas(base)]

    tarifas = conocimiento.tarifas(base)
    sin_duracion = [s["servicio"] for s in tarifas if not s.get("duracion")]
    if sin_duracion:
        problemas.append(f"sin duración en tarifas.md (se citan a 30 min): "
                         f"{', '.join(sin_duracion)}")
    if not mundo.negocio.horario:
        problemas.append("sin [horario] en negocio.toml: toma nota, pero no reserva")

    cabe, tamano = conocimiento.cabe_en(base=base)
    if not cabe:
        problemas.append(f"el conocimiento ya no cabe entero en el prompt "
                         f"({tamano} caracteres): el buscador lo trocea, pero "
                         f"conviene repasar qué hay escrito")

    # Dos citas pisándose no deberían poder existir; si existen, hay que verlo.
    if mundo.agenda is not None:
        citas = sorted(mundo.agenda.citas(), key=lambda c: (c["fecha"], c["hora"]))
        for antes, despues in zip(citas, citas[1:]):
            if antes["fecha"] != despues["fecha"]:
                continue
            fin = _agenda._minutos(antes["hora"]) + antes.get("duracion", 0)
            if fin > _agenda._minutos(despues["hora"]):
                problemas.append(f"dos citas se pisan el {antes['fecha']}: "
                                 f"{antes['hora']} y {despues['hora']}")

    caducadas = memoria.caducar(hoy=mundo.hoy)
    if caducadas:
        problemas.append(f"{len(caducadas)} ficha(s) de clientes borradas por llevar "
                         f"{memoria.CADUCA_DIAS // 365} años sin llamar")

    if not problemas:
        return None
    return Resultado("revision", "Revisión del negocio:", problemas, tipo="fallo")


TODOS = {
    "recordatorios": recordatorios,
    "resumen": resumen,
    "huecos": huecos,
    "seguimiento": seguimiento,
    "revision": revision,
}


# ---- correrlos -----------------------------------------------------------

def mundo_de(negocio, ahora: datetime | None = None) -> Mundo:
    """El mundo de verdad: la agenda del negocio, las fichas y el reloj."""
    agenda = (_agenda.Agenda(negocio.ruta.name, negocio.horario)
              if negocio.horario else None)
    return Mundo(negocio=negocio, agenda=agenda,
                 ahora=ahora or fechas.ahora(), fichas=memoria.fichas())


def correr(negocio, cuales: list[str] | None = None, ahora: datetime | None = None,
           registrar: bool = True) -> list[Resultado]:
    """Corre los agentes y devuelve lo que han encontrado.

    `registrar=False` los corre sin escribir nada: sirve para mirar qué
    dirían antes de dejar que lo digan.
    """
    mundo = mundo_de(negocio, ahora)
    resultados = []
    for nombre in (cuales or list(TODOS)):
        agente = TODOS.get(nombre)
        if agente is None:
            continue
        try:
            resultado = agente(mundo)
        except Exception as error:  # noqa: BLE001 — un agente roto no tumba a los demás
            resultado = Resultado(nombre, f"El agente «{nombre}» ha fallado: "
                                          f"{type(error).__name__}: {error}", tipo="fallo")
        if resultado is None:
            continue
        resultados.append(resultado)
        if registrar:
            avisos.registrar(resultado.tipo, resultado.texto())
    return resultados


def main() -> int:
    """`python3 agentes.py`: los corre y deja los avisos. `--seco` para mirar."""
    import argparse

    import negocio as negocios

    parser = argparse.ArgumentParser(description="Lo que trabaja cuando no suena el teléfono")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--agente", action="append", choices=sorted(TODOS),
                        help="correr solo este (se puede repetir)")
    parser.add_argument("--seco", action="store_true",
                        help="enseñar lo que dirían sin registrar ningún aviso")
    parser.add_argument("--listar", action="store_true", help="qué agentes hay")
    args = parser.parse_args()

    if args.listar:
        for nombre, agente in sorted(TODOS.items()):
            primera = (agente.__doc__ or "").strip().split("\n")[0]
            print(f"  {nombre:15} {primera}")
        return 0

    try:
        negocio = negocios.cargar(args.negocio)
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return 1

    resultados = correr(negocio, args.agente, registrar=not args.seco)
    if not resultados:
        print("Nada que contar hoy.")
        return 0
    for resultado in resultados:
        print(f"\n[{resultado.agente}] {resultado.texto()}")
    if args.seco:
        print("\n(en seco: no se ha registrado ningún aviso)")
    else:
        print(f"\n{len(resultados)} aviso(s) registrado(s). `make avisar` los manda al móvil.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
