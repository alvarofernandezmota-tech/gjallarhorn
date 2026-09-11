# gjallarhorn

Entrada por voz al diario de **midgaror**. El cuerno que se hace sonar.

> **Estado: el agente funciona de punta a punta.** Le hablas (o le escribes) y
> hace algo. Falta el modelo de Whisper instalado en la máquina donde corra, y
> el cerebro sigue siendo de reglas, no un LLM.
> Las decisiones que lo justifican son el **ADR-017** (proyecto aparte) y el
> **ADR-018** (agente, no dictáfono) de midgaror, los dos del 2026-09-11.

## Qué es

Un proyecto aparte —no una parte de bifrost— para **hablarle al diario** en vez
de teclearlo.

Y no es un dictáfono: es un **agente**. Un dictáfono copia lo que oye; un
agente entiende qué le estás pidiendo y hace algo distinto según lo que sea.
«Apunta que hoy he ido al gimnasio», «recuérdame llamar al dentista el jueves»
y «¿qué tengo mañana?» son tres acciones sobre tres modelos distintos, y las
tres suenan igual por el micrófono.

Lo que no inventa es el último tramo: escribe por el mismo contrato que usa el
bot de Telegram, `escribir_entrada` (ADR-009 de midgaror), para que siga
habiendo **un solo camino de escritura** al diario.

## Las tres capas

| Capa | Qué es | Estado |
|---|---|---|
| **1. Acciones** | Qué sabe hacer sobre el diario | ✅ hecha |
| **2. Cerebro** | Qué acción toca, a partir de lo que dijiste | ✅ de reglas; el LLM entra por la misma puerta |
| **3. Oreja** | Audio → texto, con Whisper en local | ✅ escrita; falta instalar el modelo |
| **3b. Teléfono** | Llamar y hablar | ❌ bloqueado (ADR-015) |

Que se puedan separar es lo que hace esto viable: las acciones son las mismas
tanto si la voz llega por teléfono, por una nota de Telegram o por un fichero.

### La capa 1, hoy

`acciones.py` — siete cosas que el agente sabe hacer, cada una envolviendo una
función de midgaror **que ya existe y ya está probada**:

| Acción | Envuelve |
|---|---|
| `apuntar_en_diario` | `bifrost_bridge.escribir_entrada` |
| `crear_tarea` | `tareas.agregar` |
| `crear_cita` | `agenda.agregar` |
| `marcar_habito` | `habitos.marcar` |
| `apuntar_registro` | `registro.apuntar` |
| `leer_diario` | `bifrost_bridge.leer_entrada` |
| `que_hay_hoy` | los tres resúmenes juntos |

```python
from acciones import catalogo, ejecutar

catalogo()                       # las herramientas en el formato que usan los LLM
ejecutar("crear_tarea", texto="llamar al dentista el jueves")
# → 'Tarea 1 creada para el 2026-09-17: llamar al dentista.'
```

`ejecutar` devuelve **una frase**, no un objeto: es lo que el agente dirá en
voz alta. Y solo pasa los argumentos declarados en el esquema, así que un
modelo que se invente un parámetro se queda sin él —incluido `ruta`, que es el
que decidiría dónde se escribe—.

## Por qué no vive dentro de bifrost

bifrost es el bot de Telegram y está en producción escribiendo el diario.
Tres motivos, en orden de peso:

1. **Un fallo en la voz no puede dejar mudo al bot que ya funciona.** Colgarle
   transcripción —y más adelante un servidor HTTP— amplía su superficie justo
   donde menos conviene.
2. **Son dos entradas distintas al mismo sitio**, no una capa de la otra.
   Compartir destino no las hace el mismo programa.
3. **El ciclo de vida no coincide.** bifrost se toca poco y con miedo, porque
   escribe. La voz va a ser prueba y error durante semanas.

## Lo que viene

1. **El cerebro.** Convertir «apunta que he ido al gimnasio» en
   `marcar_habito("gimnasio")` es lo que hace un LLM con llamada a
   herramientas. Falta decidir cuál, y no es cuestión de gusto: **local**
   (Ollama, los datos no salen, cuesta CPU que hay que medir) o **API**
   (funciona mejor hoy, y manda fuera lo que dices de tu vida). Se decide
   midiendo, con la capa 1 ya hecha.
2. **La transcripción local.** Audio → texto con Whisper o equivalente, sobre
   el hardware de casa.
3. **La telefonía.** Bloqueada, ver abajo.

Antes que la 3 hay una entrada de audio que ya existe y no cuesta nada: la
**nota de voz de Telegram**. Permite tener el agente funcionando de verdad
antes de resolver el teléfono.

### Por qué la telefonía está bloqueada

Un proveedor de telefonía trabaja con **webhooks entrantes**: llama a una URL
pública cuando entra la llamada. Y el ADR-015 de midgaror decidió, con su
motivo escrito, que **en el router no se abre nada**.

Que gjallarhorn sea un repo aparte **no resuelve eso**: el router es el mismo.
Hace falta un ADR que diga cómo entra ese webhook —relé en la nube, Tailscale
Funnel, u otra cosa— antes de escribir una línea de telefonía.

## Dos reglas que no se negocian

- **El audio no sale de casa.** La transcripción es local. Mandar el diario
  hablado a una API de terceros va en contra de todo lo decidido sobre dónde
  viven estos datos (ADR-016 de midgaror).
- **No se abre un segundo camino de escritura.** Todo entra por
  `escribir_entrada`. Es lo que hace que los arreglos del diario —el reloj
  único, el JSON legible— valgan aquí sin tocarlos.

## Estructura

```
gjallarhorn/
├─ AGENTS.md               # instrucciones para sesiones de IA
├─ CONTEXT.md              # propósito y decisiones de arquitectura
├─ README.md               # esto
├─ agente.py               # el agente entero, y la orden de terminal
├─ acciones.py             # capa 1: qué sabe hacer
├─ cerebro.py              # capa 2: qué acción toca, de reglas por ahora
├─ voz.py                  # capa 3: la oreja, Whisper en local
├─ midgaror.py             # dónde está midgaror y cómo se importa. En un solo sitio
├─ ruff.toml               # las mismas reglas de lint que midgaror y bifrost
├─ tests/                  # 43 pruebas, contra los módulos reales de midgaror
├─ docs/
│  └─ procedimientos/      # un .md por procedimiento (ADR-004)
└─ scripts/                # automatización de procedimientos (todavía vacío)
```

Los módulos de librería van en la raíz, como en bifrost (`bot.py`, `utils/`).
`scripts/` es para lo que automatiza un procedimiento, con el mismo nombre base
que su `.md` (ADR-004).

## Probarlo

Sin grabar nada, para ver el cerebro y las acciones:

```bash
MIDGAROR_RAIZ=/ruta/a/midgaror MIDGAROR_DATOS=/tmp/pruebas \
  python3 agente.py --texto "recuérdame llamar al dentista el jueves"
# → Tarea 1 creada para el 2026-09-17: llamar al dentista.
```

`MIDGAROR_DATOS` (ADR-016) manda la escritura a un sitio de mentira, así que se
puede trastear sin tocar el diario de verdad.

Con audio, en la máquina donde esté el modelo:

```bash
pip install faster-whisper
python3 agente.py nota.ogg
```

## Pruebas

```bash
MIDGAROR_RAIZ=/ruta/a/midgaror python3 -m unittest discover -s tests
```

Van contra los módulos **reales** de midgaror, no contra dobles: lo que se
comprueba es justamente que envolverlos sale bien. Lo de mentira son las rutas,
que van a un temporal — y hay una prueba dedicada a que eso siga siendo cierto,
porque escribir en el diario de verdad es el error que no se puede cometer ni
una vez.

Cuando gjallarhorn sea submódulo de midgaror, estas pruebas se encadenan en
`scripts/verificar.py`. Hasta entonces se corren a mano, y **una comprobación
saltada no es una comprobación pasada**.

## Relación con el ecosistema

- Submódulo de **midgaror**, en `proyectos/`, igual que bifrost.
- Escribe por `bifrost_bridge.escribir_entrada` (ADR-009).
- Respeta `MIDGAROR_DATOS` (ADR-016) sin saber nada de él: eso lo resuelve
  midgaror.
