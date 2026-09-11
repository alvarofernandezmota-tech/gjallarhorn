# gjallarhorn

Un recepcionista telefónico: atiende la llamada, informa de tarifas y toma la
cita. **Proyecto independiente, sin dependencias de ningún otro repo.**

> **Estado: funciona de punta a punta por voz, desde un móvil.** Conversa con
> memoria, reserva contra el horario y avisa por Telegram. Falta la telefonía
> —que una llamada de verdad entre— y eso depende de un número: cuánto tarda
> Whisper en la máquina donde viva (`make medir`).

## Qué hace

```
audio → voz.escuchar → Conversacion.atender → voz.hablar → audio
                              ↓ al colgar
                        avisos.registrar
```

Una llamada normal, tal cual la atiende hoy (`python3 telefonia.py --simular`
la reproduce por teclado, sin teléfono):

```
— Hola, buenas                     Dígame, ¿en qué puedo ayudarle?
— ¿Cuánto vale un tinte?           Tengo varias: Tinte 45 €; Corte y tinte 60 €. ¿Cuál le interesa?
— El tinte                         Tinte: 45 €, unos 90 min.
— ¿Y cuánto tarda?                 Tinte: 45 €, unos 90 min.
— Vale, pues quiero cita           Muy bien, una cita de tinte. ¿Qué día le viene bien?
— El jueves por la tarde           Perfecto, el jueves 17 por la tarde. ¿A qué hora?
— A las cinco                      ¿A nombre de quién se la apunto?
— ¿Aceptáis tarjeta?               Sí, tarjeta y efectivo. ¿A nombre de quién se la apunto?
— Marta                            Reservada la cita de tinte el jueves 17 a las cinco de la
                                   tarde, a nombre de Marta. Le esperamos. ¿Algo más?
— A nombre de Lucía                Anotado: la cita queda a nombre de Lucía.
— No, nada más, gracias            Gracias a usted. ¡Hasta luego!        (y cuelga)
```

**Recuerda.** El tinte del primer turno sigue vivo en el quinto, «por la
tarde» hace que «a las cinco» sean las cinco de la tarde sin volver a
preguntarlo, y una pregunta suelta en mitad de la cita se contesta y se retoma
donde estaba. Sin memoria, esta llamada se cae en el segundo turno.

Lo que reconoce: **precio** (y «¿cuánto tarda?»), **cita**, **anular** o
**cambiar** una cita, **horario**, cualquier pregunta que esté escrita en
`faq.md` (tarjeta, dónde, si hace falta cita…), un **saludo**, la
**despedida** y, para todo lo demás, el **recado**. Y una regla por encima de
todas:

> **Un precio sale de la tabla o no sale.** Nunca aproximado, nunca una
> horquilla. Si el servicio no está, dice que no lo sabe y toma el recado.
> Cantar un precio equivocado por teléfono cuesta dinero y credibilidad.

Eso no depende del modelo que se use: la consulta la resuelve una tabla, no un
generativo. Un LLM podrá redactar mejor la frase, **el número no lo pone él**.

## Independiente

Nada de esto importa otro repo. Lo que necesita, lo tiene:

| | |
|---|---|
| `fechas.py` | cuándo quiere la cita, **siempre hacia delante** |
| `almacen.py` | JSON con versión de esquema y escritura atómica |
| `voz.py` | Whisper y Piper, las dos **en local** |

Lo de `fechas.py` no es solo independencia: un parser de diario resuelve hacia
**atrás** —«el lunes» es el que pasó— y un recepcionista siempre mira hacia
delante. Nadie reserva cita para el martes pasado.

## Dar de alta un negocio: copiar una carpeta

```bash
cp -r negocios/peluqueria negocios/mi-negocio
```

| Fichero | Qué cambia |
|---|---|
| `tarifas.md` | la tabla de precios — **de aquí y solo de aquí salen los números** |
| `faq.md` | horario y lo que se pregunta por teléfono |
| `negocio.toml` | el nombre, el saludo, la despedida y **el horario** |
| `frases.toml` | **lo que contesta el agente y lo que entiende del cliente** |

**No se toca código.** Quien lleva el negocio tiene que poder cambiar un
precio, o la forma de despedirse, sin llamar a nadie; y eso solo es cierto si
no hay que abrir un `.py`.

Todo menos `tarifas.md` y `faq.md` es opcional: una carpeta con los dos
Markdown ya es un negocio.

### `[horario]`: con esto reserva, sin esto toma nota

```toml
[horario]
lunes = []                              # cerrado
martes = ["10:00-14:00", "16:30-20:00"]
sabado = ["09:00-14:00"]
```

Con el horario escrito, el agente **reserva de verdad**: comprueba que abrís
ese día, que la hora cae dentro y que nadie tiene ya ese hueco —un tinte de
90 min a las 10 ocupa hasta las 11:30, y un corte a las 11 no cabe—. Si no
cabe, ofrece los huecos que sí hay, cerca de lo que pidió:

```
— El lunes a las cinco     El lunes 14 estamos cerrados. Tengo hueco el martes 15 a las
                           diez de la mañana, el miércoles 16… ¿Le viene bien alguno?
— El jueves a las seis     A esa hora ya tengo a alguien. El jueves 17 me queda las seis
                           y media de la tarde, las siete… ¿Le viene bien alguno?
```

Y resuelve solo el «¿a las cinco de la mañana o de la tarde?» cuando solo una
de las dos cae en horario. Las citas se ven con `python3 agenda.py`.

Sin `[horario]`, se toma nota y se promete confirmar, como antes. A propósito:
antes que reservar contra un horario que nadie ha escrito, mejor no reservar.

### `frases.toml`: las palabras también se editan

Dos secciones. `[dice]` es lo que contesta el agente, con huecos que se
rellenan solos:

```toml
[dice]
pide_dia = "Muy bien, una cita{servicio}. ¿Qué día le viene bien?"
despedida = "Gracias a usted. ¡Hasta luego!"
```

`[entiende]` es cómo puede pedir las cosas quien llama — aquí entra la forma
de hablar de cada sitio:

```toml
[entiende]
precio = ["cuanto", "cuanto vale", "cuesta", "precio", "me saldria"]
```

(«vale» a secas no está a propósito: «vale, pues nada, gracias» no es una
pregunta de precio. Se aprendió oyéndolo.)

Lo que no pongas usa el valor de fábrica. Y **una errata no tumba una
llamada**: un `{fehca}` mal tecleado se avisa al arrancar, y si se cuela, el
agente dice la frase de fábrica y deja un aviso. Lo que no puede fallar no se
deja en manos de que alguien lo escriba bien.

Dos cosas no se pueden cambiar desde ahí, **a propósito**: el saludo —va en
`negocio.toml` y se comprueba que avise de que es automático— y los precios,
que salen de la tabla y de ningún otro sitio.

```bash
python3 recepcion.py --negocio mi-negocio                        # por teclado
python3 recepcion.py --negocio mi-negocio --audio llamada.ogg --hablar
```

### El aviso de que es automático no se puede quitar

Puedes poner tu propio saludo. Si **no** dice que se habla con un sistema
automático, se le añade al cargarlo:

```
saludo = "Hola, ha llamado a la peluquería."
   ↓
"Hola, ha llamado a la peluquería. Le atiende un asistente automático."
```

No es un descuido que se pueda cometer editando un fichero de texto.

## El teléfono de verdad

Un proveedor de telefonía que hable TwiML (Twilio, Telnyx) recibe la llamada
en tu número y hace un POST a `/telefono/entrada`; el servidor le contesta
con lo que decir y se queda escuchando. **Cada llamada es su conversación**:
pueden entrar dos a la vez. Quien ya llamó y dio su nombre, la próxima vez
oye «Hola, Marta» y no se le vuelve a preguntar.

```bash
# .env: GJALLARHORN_TELEFONO_TOKEN=<el Auth Token del proveedor>
make arrancar
make funnel          # publica SOLO el puerto del teléfono, sin abrir el router
```

Y en el proveedor, como webhook de voz, `https://<máquina>.<tailnet>.ts.net/telefono/entrada`.

### Dos puertos, y la diferencia es de seguridad

```
8080  la demo: la página, /hablar, /colgar   → tailscale serve   (solo tu tailnet)
8081  solo /telefono/*                        → tailscale funnel  (internet)
```

El webhook tiene que ser alcanzable desde internet; **la demo no puede
serlo**: `/hablar` arranca Whisper con el audio que le manden y `/colgar`
escribe en la agenda de un negocio real. Publicar un puerto con las dos
cosas dentro abre lo segundo para conseguir lo primero.

Son dos servidores con **dos tablas de rutas distintas**. Que la demo no
salga a internet no depende de mirar una cabecera ni de confiar en Tailscale:
el puerto que se publica no sabe servirla. `make funnel` publica el que toca
y **se niega si no hay token**; `make sin-funnel` deja de publicar.

Aquí **no se usan Whisper ni Piper**: el proveedor transcribe y sintetiza en
su lado. Va en décimas de segundo donde Whisper `small` tarda casi tres, y
para el teléfono esa es la diferencia entre servir y no servir. El audio
pasa por el proveedor, pero eso pasa con cualquier número: quien te da la
línea oye la línea. Lo que sigue siendo de aquí es **la conversación, los
precios y la agenda**: ni una palabra de lo que se le dice al cliente la
pone el proveedor.

Cada petición viene firmada con el token; la que no, 403 sin mirar nada.
Sin token no hay webhook: antes que abierto, apagado.

## Un LLM, opcional, y solo donde las reglas no llegan

Las reglas cubren precio, cita, horario y despedida; lo demás es «tomo nota».
Con `ANTHROPIC_API_KEY` en `.env`, cuando las reglas **no** entienden una
frase se le pregunta a Claude qué quería decir, y contesta con **datos de
forma fija** —intención, servicio de la tabla, cuándo, nombre— que se
atienden por el mismo camino que una frase entendida por reglas.

```
— Oye, ¿hacéis lo del color ese?     → Tinte: 45 €, unos 90 min.   ← el precio, de la tabla
— ¿Hacéis alisado?                    → No tengo ese servicio…       ← no está: no se inventa
```

El modelo **no redacta lo que se le dice al cliente y no pone ningún
número**: su salida es un JSON de cuatro campos, y un servicio que no esté en
la tabla se descarta diga lo que diga. Si falla o tarda más de cuatro
segundos, las reglas siguen solas: una llamada nunca se cae por esto.

Encenderlo tiene un precio que hay que decir: **el texto de lo que dijo el
cliente sale de casa** hacia la API. El audio no. Por eso viene apagado.
`make cerebro FRASE="…"` enseña qué entiende y cuánto tarda.

## Los avisos llegan al móvil

Cada cita reservada, cada recado y cada fallo se apunta en `avisos.json` y,
si hay Telegram configurado, **llega al móvil en el momento**, en un hilo
aparte para no sumarle la red al tiempo de la llamada.

```bash
cp .env.example .env      # y rellena token y chat
make telegram-prueba      # ¿llega?
```

Un aviso no se da por visto hasta que Telegram confirma que lo tiene: si la
red falla, sale en el siguiente envío. Y las tarifas no se mandan por defecto:
veinte «preguntó el precio del corte» al día son ruido, y el ruido es lo que
hace que se deje de mirar. `python3 avisos.py` los lista todos.

## Operarlo: `make`

```
make instalar      venv + dependencias + modelos, de una vez
make voz           ¿oye y habla esta máquina? versiones y milisegundos
make medir         cuánto tarda en contestar · MODELO=base para el modelo pequeño
make arrancar      servicio systemd: siempre encendido, se reinicia si cae
make estado        ¿vivo? ¿qué modelo? últimas citas y avisos
make diagnostico   el informe entero, para pegarlo de una vez
make log           el log del servicio, en vivo
make avisar        mandar al móvil los avisos pendientes
make nuevo         dar de alta otro negocio: make nuevo NEGOCIO=mi-negocio
make telefono-prueba  una llamada por teclado, como la vería el proveedor
make auto          que la máquina se actualice sola desde GitHub cada 5 min
make serve         la demo, visible solo en tu tailnet (para el móvil)
make funnel        publicar SOLO el webhook del teléfono
make sin-funnel    dejar de publicar: nada sale a internet
```

`make` a secas lista todo. Tras un `git pull` o editar el negocio: `make
reiniciar`, que regenera la unidad de systemd si la plantilla ha cambiado —si
no, el servicio seguiría arrancando con los argumentos viejos sin decirlo.

## La voz, de punta a punta

```
audio → Whisper → recepcion.atender → Piper → audio
```

Las dos **locales**, y por el mismo motivo: por ahí pasa lo que se le dice a un
cliente y lo que el cliente cuenta. Las dos detrás de una interfaz de una
función, para poder probar todo lo de encima sin descargar modelos de cientos
de megas.

En la máquina donde corra: `pip install faster-whisper piper-tts`. Los dos
**descargan su modelo la primera vez**, así que ese arranque es lento y necesita
salida a internet. Después ya no.

Si la síntesis revienta, **la llamada sigue registrada**. Perder la
contestación es malo; perder el rastro de que alguien llamó preguntando un
precio, peor.

## Estructura

```
gjallarhorn/
├─ recepcion.py            quién atiende, y Conversacion: la llamada con memoria
├─ frases.py               lo que dice y lo que entiende, editable por negocio
├─ agenda.py               los huecos: reserva de verdad contra el horario
├─ avisar.py               los avisos, al móvil por Telegram
├─ cerebro.py              el LLM, opcional: entiende, no habla ni pone precios
├─ telefonia.py            el webhook del número de verdad, una conversación por llamada
├─ diagnostico.py          qué le pasa a esta máquina, en veinte líneas
├─ Makefile                instalar, arrancar, medir, estado: un comando cada uno
├─ negocio.py              un negocio = una carpeta
├─ conocimiento.py         tarifas y FAQ, sin RAG (y por qué)
├─ voz.py                  la oreja (Whisper) y la boca (Piper), las dos locales
├─ avisos.py               el rastro de las llamadas, ordenado
├─ fechas.py               cuándo quiere la cita, siempre hacia delante
├─ almacen.py              los JSON, con escritura atómica
├─ medir_voz.py            cuánto tarda en contestar, sin teléfono ni tarjeta
└─ negocios/peluqueria/    el negocio: tarifas.md, faq.md, negocio.toml, frases.toml
```

## Dónde guarda sus datos

- `GJALLARHORN_DATOS` para los avisos; `GJALLARHORN_CONOCIMIENTO` para las
  tarifas. Sin ellas, dentro del repo.
