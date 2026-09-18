# gjallarhorn

Un recepcionista telefónico: atiende la llamada, informa de tarifas y toma la
cita.

El cerebro —entender, decidir y recordar— vive aparte, en
[hugin](https://github.com/alvarofernandezmota-tech/hugin), que entra aquí
como submódulo ([ADR-019]). Esa separación es a propósito: hugin **no sabe
que gjallarhorn existe**, así que el mismo cerebro sirve para el teléfono o
para cualquier otro canal. Lo que hay en este repo es el canal —audio,
telefonía— y las herramientas del dueño del negocio.

> **Para clonarlo hace falta traer el submódulo**, o `hugin/` queda vacío y
> el primer mensaje revienta con un `ImportError` que no dice que falte un
> `git submodule`:
>
> ```bash
> git clone --recurse-submodules https://github.com/alvarofernandezmota-tech/gjallarhorn.git
> ```
>
> Si ya lo has clonado sin eso: `git submodule update --init --recursive`.
> Y si hugin no es accesible para ti, el cerebro no se puede traer — pide
> acceso antes de seguir.

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

Una llamada normal, tal cual la atiende hoy (`python3 telefono/telefonia.py --simular`
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
| `mente/fechas.py` | cuándo quiere la cita, **siempre hacia delante** |
| `guardado/almacen.py` | JSON con versión de esquema y escritura atómica |
| `telefono/voz.py` | Whisper y Piper, las dos **en local** |

Lo de `mente/fechas.py` no es solo independencia: un parser de diario resuelve hacia
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
de las dos cae en horario. Las citas se ven con `python3 negocio/agenda.py`.

**De qué es la cita se pregunta una vez**, y no es por curiosidad: un tinte
dura hora y media y un corte media hora, así que sin saberlo los huecos que
se ofrecen son los que no son y la tarde se descuadra. Si no lo dice, se
sigue igual y se apunta sin él.

Quien pregunta qué hay, lo oye; y a «¿a qué hora?» se puede contestar como se
contesta por teléfono:

```
— ¿Tenéis hueco el jueves por la tarde?   Muy bien. ¿Para qué servicio se la apunto?
— Un tinte                                El jueves 17 tengo las cuatro y media, las cinco o
                                          las cinco y media de la tarde. ¿Cuál le viene bien?
— El primero                              ¿A nombre de quién se la apunto?
— Cuando podáis                           Lo más pronto que tengo es hoy a las doce, mañana a
                                          las nueve o el martes 15 a las diez. ¿Le viene bien alguno?
— Las cinco menos cuarto                  (04:45 → con agenda, «a esa hora no estamos abiertos»)
— Sobre las cinco                         ¿Las cinco de la tarde?
```

«A las 5:30», que es como transcribe el proveedor «las cinco y media», **no**
se da por acotado: se pregunta si es de la tarde, como con «las cinco».

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

`[sinonimos]` es cómo llama la gente a lo que hay en `tarifas.md`. Nadie dice
«corte de caballero»: dice «cortarme el pelo» o «un corte de hombre».

```toml
[sinonimos]
corte = ["cortarme", "cortar el pelo", "corte de pelo"]
caballero = ["hombre", "chico", "señor"]
mechas = ["reflejos", "balayage"]
```

Con eso, «¿cuánto vale cortarme el pelo?» encuentra los cortes de la tabla, y
«reflejos» son las mechas. Sin tocar la tabla ni el código.

Otras dos cosas que se atienden solas: «¿cómo?, ¿me lo repite?» repite lo
último tal cual, y «¿eres un robot?, ¿puedo hablar con alguien?» dice la
verdad —que es un asistente automático— y toma el recado. Nunca se hace pasar
por una persona.

Lo que no pongas usa el valor de fábrica. Y **una errata no tumba una
llamada**: un `{fehca}` mal tecleado se avisa al arrancar, y si se cuela, el
agente dice la frase de fábrica y deja un aviso. Lo que no puede fallar no se
deja en manos de que alguien lo escriba bien.

Dos cosas no se pueden cambiar desde ahí, **a propósito**: el saludo —va en
`negocio.toml` y se comprueba que avise de que es automático— y los precios,
que salen de la tabla y de ningún otro sitio.

```bash
python3 mente/recepcion.py --negocio mi-negocio                        # por teclado
python3 mente/recepcion.py --negocio mi-negocio --audio llamada.ogg --hablar
```

### Añadir conocimiento es añadir un `.md`

`tarifas.md` y `faq.md` son los dos que pide la plantilla, pero **cualquier
`.md` de la carpeta del negocio es conocimiento**. Un `servicios.md` con el
aparcamiento, los productos o las bodas se contesta igual, sin tocar código:

```
— ¿Tenéis aparcamiento?     Hay parking público a cincuenta metros. Los sábados
                            por la mañana suele estar lleno…
— ¿Usáis amoniaco?          Trabajamos con tintes sin amoniaco. Si tienes alergia…
```

Lo busca `mente/rag.py`: parte cada fichero en párrafos con su título, y encuentra
el que contesta. **En local, sin embeddings y sin base vectorial** —el porqué
está escrito en la cabecera del fichero— y se lo dice tal cual lo escribió el
dueño, sin parafrasear.

Y se calla cuando no está claro, que es la mitad del trabajo: si dos párrafos
empatan o ninguno cubre la pregunta, toma el recado. Los umbrales no están
puestos a ojo: salen de un banco de frases etiquetadas (`TestElBanco`) contra
el que se probaron todas las combinaciones.

```bash
python3 mente/rag.py "¿se puede pagar con tarjeta?"   # qué encuentra y con cuántos puntos
python3 mente/rag.py --todo                           # los párrafos indexados
```

Los precios **no** salen de ahí: las filas de la tabla se quitan antes de
indexar, para que ningún camino pueda acabar leyendo un precio «por parecido».

### Lo que recuerda de quien llama, y lo que olvida

Quien ya llamó tiene una ficha: su nombre, cuántas veces ha llamado, qué
suele pedir y a qué hora suele venir. Con eso, la segunda llamada no empieza
de cero:

```
— (suena)                   Hola, Marta. Ha llamado a la peluquería…
— Quería lo de siempre      Muy bien, tinte como siempre. ¿Qué día le viene bien?
— El jueves, cuando podáis  El jueves 17 por la tarde tengo las cuatro y media,
                            las cinco o las cinco y media. ¿Cuál le viene bien?
```

«Lo de siempre» son **dos veces el mismo servicio**, no una: que alguien se
tiñera una vez no lo convierte en su costumbre. Y la tabla manda sobre la
ficha: si el servicio ya no está en `tarifas.md`, no se le ofrece.

Esto son datos personales, así que `mente/memoria.py` tiene tres reglas escritas en
el código:

| | |
|---|---|
| solo lo que sirve | nombre, servicio, franja y cuentas. Ni transcripciones ni texto libre |
| se olvida solo | `caducar()` borra las fichas con dos años sin llamar |
| se borra de verdad | `make olvidar TELEFONO=+34600…` quita la ficha entera |

Y lo de siempre: **un informe no lleva nombres**. `make diagnostico` dice
cuántas fichas hay, no de quién.

```bash
make clientes                        # las fichas (esto sí lleva nombres: es para ti)
make olvidar TELEFONO=+34600000000   # borrar una entera
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

### Cada bot es suyo, y cada uno habla a su manera

El repo trae **dos** ejemplos a propósito: `negocios/peluqueria` trata de
usted y `negocios/taller` tutea. Es el mismo código:

```
— Quiero cita el jueves          Peluquería: Perfecto, el jueves 17. ¿A qué hora le viene bien?
                                 Taller:     Vale, el jueves 17. ¿A qué hora?
— Me llamo Álvaro                Peluquería: Le apunto la cita… Le esperamos.
                                 Taller:     Te apunto la cita… Aquí te esperamos.
```

Para oír todo lo que va a decir el tuyo, y que no se le escape un «usted» en
mitad de un bot que tutea:

```bash
make frases NEGOCIO=taller
```

Lo dice frase por frase, marca cuáles son suyas y cuáles usa de fábrica, y
avisa si alguna se ha quedado del otro lado. Pasa solo: lo que no escribas en
tu `frases.toml` sale de las de fábrica, que tratan de usted.


Un negocio es un bot, y **todo lo suyo es suyo**:

| | |
|---|---|
| `negocio.toml` | su nombre, su saludo, su despedida, su voz, su horario |
| `frases.toml` | lo que dice y lo que entiende: su forma de hablar y sus sinónimos |
| `tarifas.md`, `faq.md`, cualquier `.md` | lo que sabe |
| `datos/<negocio>/agenda.json` | sus citas |
| `datos/<negocio>/clientes.json` | quién le llama y qué suele pedir |
| `datos/<negocio>/avisos.json` | su registro de llamadas |

Dos negocios son dos carpetas y dos procesos, y no se mezclan: la peluquería
no saluda por su nombre a quien llamó al taller, y los avisos de cada uno van
a su sitio. Antes los datos eran de la máquina y no del negocio; si vienes de
esa versión, la primera vez que arranques se mudan solos y te lo dice.

### Tu negocio no tiene por qué vivir dentro del repo

`negocios/peluqueria/` es el **ejemplo** que viene con el código. Tu negocio
puede vivir donde quieras:

```bash
export GJALLARHORN_NEGOCIOS=~/negocios      # en .env o en el servicio
cp -r negocios/peluqueria ~/negocios/mi-negocio
```

Con eso, tus precios, tu saludo y tus preguntas frecuentes **no se suben a
GitHub** —este repo es público— y un `git pull` no te los pisa nunca. El
código no cambia: lee la carpeta que le digas.

Y si prefieres tenerlo dentro del repo, revisa antes que el repo sea privado.

## El panel: el día, desde el móvil

El dueño se enteraba de las cosas por Telegram —avisos sueltos, según pasan—
y por la terminal. Para quien tiene una peluquería eso no vale: lo que hace
falta es una pantalla que conteste de un vistazo a «¿qué tengo hoy?».

```
make serve            # y en el móvil: https://<máquina>.<tailnet>.ts.net/panel
make panel            # lo mismo, en la terminal
```

Enseña las citas de hoy y de mañana con su hora, servicio, nombre y teléfono,
los huecos que quedan libres, lo que se espera facturar —sumando **solo** los
precios de la tabla, y diciendo aparte cuántas citas no tienen precio— y los
últimos avisos. Y deja hacer una cosa: anular una cita, con confirmación y
dejando rastro en los avisos.

**Vive en el puerto privado y solo ahí.** Aquí salen nombres y teléfonos de
clientes, que es justo lo que `make diagnostico` no enseña nunca: el
diagnóstico se pega en un chat, y el panel es la libreta del dueño dentro de
su tailnet. El puerto que se publica en internet no tiene ni ruta para esto,
y hay pruebas que lo comprueban.

## ¿Está listo para coger llamadas?

Antes de dar un número hay seis cosas que mirar, repartidas en seis sitios.
Una orden las junta:

```bash
make revisar
```
```
 ✅ tarifas: 9 servicio(s)
 ✅ conocimiento: 10 párrafo(s) que puede contestar
 ✅ frases: trata de usted en todo
 ✅ horario: abre 5 día(s) por semana
 ⚠️  copias: ninguna todavía
 ❌ teléfono: sin token
      GJALLARHORN_TELEFONO_TOKEN en .env; sin él no hay webhook

❌ No está listo para coger llamadas: 1 cosa(s) rotas.
```

Sale 1 si algo está roto, así que vale para un gancho o un cron. Un **fallo**
es lo que hace que una llamada salga mal; un **aviso** es lo que funciona
pero conviene mirar.

## Copias: lo peor es perder las citas

Una copia al día de las citas, los clientes y los avisos, dentro de la
carpeta del negocio y en JSON sin comprimir —el día malo no quieres depender
de una herramienta para abrir tu agenda—:

```bash
make copia            # la de hoy, y tira las viejas (se guardan 14)
make copias           # qué copias hay
python3 guardado/copias.py --restaurar 2026-09-11
```

Restaurar **no borra lo que hay**: antes guarda el estado actual en
`copias/antes-de-restaurar-…`. Restaurar la copia equivocada y quedarse sin
las dos versiones es un error que solo se comete una vez.

La hace sola uno de los agentes cada mañana, y solo habla si algo falla. No
sustituye a una copia fuera de la máquina: si arde la máquina, arden las
copias. Para eso, `GJALLARHORN_DATOS` a una carpeta que ya sincronices.

## Lo que no supo contestar

Un recepcionista nuevo pregunta: «oye, me han llamado tres veces preguntando
por las uñas, ¿eso lo hacemos?». Esto es ese momento, y es lo que hace que
el bot mejore con el uso:

```bash
make aprender
```
```
Lo que el agente no supo contestar (últimos 30 días):

preguntaron algo que no está escrito en ningún sitio:
  «¿hacéis uñas?» (3 veces) → faq.md
preguntaron por un servicio que no está en la tabla de precios:
  «¿cuánto vale un masaje?» (2 veces) → tarifas.md
```

Escribes esas dos cosas en el fichero que te dice y a partir de ahí las
contesta solo. **No aprende por su cuenta**, a propósito: aprender solo aquí
sería inventarse respuestas, y lo que sabe el negocio lo escribe el negocio.

Sale también en el panel, y uno de los agentes lo manda al móvil cuando algo
se repite. Las preguntas dichas de tres formas distintas se agrupan en una
línea: se agrupan por la palabra que más se repite entre lo que te preguntan.

## El teléfono de verdad

Un proveedor de telefonía que hable TwiML (Twilio, Telnyx) recibe la llamada
en tu número y hace un POST a `/telefono/entrada`; el servidor le contesta
con lo que decir y se queda escuchando. **Cada llamada es su conversación**:
pueden entrar dos a la vez. Quien ya llamó y dio su nombre, la próxima vez
oye «Hola, Marta» y no se le vuelve a preguntar.

#### Los dos proveedores no firman igual

Esto es lo que más tiempo hace perder, porque falla en silencio: el webhook
arranca, y luego **todas** las llamadas se caen con un 403.

| | Twilio | SignalWire | Telnyx |
|---|---|---|---|
| Qué firma | HMAC-SHA1 de la URL + los campos | **el mismo HMAC** | Ed25519 sobre `marca\|cuerpo` |
| Con qué | el Auth Token | su Signing Key | su clave privada |
| Qué pones tú | ese Auth Token | esa Signing Key | la **clave pública** del portal |
| Cabecera | `X-Twilio-Signature` | `X-SignalWire-Signature` | `telnyx-signature-ed25519` |
| En el `.env` | `GJALLARHORN_TELEFONO_TOKEN` | el mismo, o `…_CLAVE_SIGNALWIRE` | `…_CLAVE_PUBLICA` |

SignalWire es compatible con TwiML a propósito —su LaML es un clon— y firma
con el mismo algoritmo, hasta el punto de que su propia librería usa el
validador de Twilio por dentro. Aquí eso se traduce en una cabecera más y
cero criptografía nueva. Si es tu único proveedor, su Signing Key va en
`GJALLARHORN_TELEFONO_TOKEN` y no hace falta nada más.

En Telnyx la clave pública está en Keys & Credentials > Public Key. **No es
la API Key**: la API Key (`KEY0197…`) ahí no vale para nada. `make revisar`
distingue los dos casos y te lo dice antes de dar el número a nadie.

No hay que elegir en la configuración: se mira la cabecera que trae cada
petición (`X-Twilio-Signature` o `telnyx-signature-ed25519`) y se valida con
la que corresponda. Una petición sin firma ninguna no se valida «con lo que
haya»: se rechaza.

De Telnyx se comprueba además la marca de tiempo, con cinco minutos de
margen. Sin eso, una petición buena que alguien grabe vale para siempre y se
puede repetir la misma llamada mil veces.

```bash
make lanzar          # de aquí a la primera llamada, paso a paso
```

Hace los seis pasos por orden y comprueba cada uno antes de seguir: te pide
la clave del proveedor y **la rechaza si no sirve** (el error más fácil es
pegar la API Key de Telnyx donde va la clave pública), arranca el servicio,
publica solo el puerto del teléfono, te imprime las dos URLs **enteras**
para pegarlas en el portal, y se queda mirando hasta que entra la primera
llamada. No imprime ningún `<hueco>` que haya que traducir a mano.

A mano, si prefieres verlo por partes:

```bash
make revisar         # ¿está listo? dice qué proveedor ha cogido
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

Las reglas y el buscador cubren lo que se pide por teléfono. Para lo que no
—«oye, que me han dicho que hacéis lo del alisado ese»— entra Claude, y
**solo para devolver datos**:

```
intencion   precio | cita | anular | cambiar | horario | despedida | otro
servicio    uno de los de tarifas.md, o ninguno
cuando      «el jueves a las cinco», tal cual lo dijo
franja      manana | tarde | noche
nombre      si lo dio
confianza   alta | media | baja
```

Con eso, `mente/recepcion.py` hace lo mismo que con una frase que las reglas sí
entienden: el precio sale de la tabla, la fecha la resuelve `mente/fechas.py`, la
agenda dice si cabe. **El modelo no redacta lo que se dice ni pone ningún
número**, y por eso su salida es un JSON de seis campos y no una frase. No
hay ningún `contestar()`, y no es un olvido: el día que redacte, redactará
precios.

Ve tres cosas: la frase, **los últimos turnos de la llamada** (sin ellos «¿y
el jueves?» no es nada) y **lo que el negocio tiene escrito sobre eso**, que
le pasa `mente/rag.py`.

Y tiene tres frenos:

| | |
|---|---|
| tiempo | 4 s y sin reintentos: una pausa larga al teléfono es una llamada colgada |
| gasto | `TOPE_CONSULTAS` por llamada; pasado eso, reglas solas |
| confianza | si el modelo dice que está adivinando, se descarta |

### Dos motores, y no dan lo mismo

```bash
# .env, una de las dos:
GJALLARHORN_LLM=anthropic   # + ANTHROPIC_API_KEY=sk-ant-…   Claude, en la nube
GJALLARHORN_LLM=ollama      # un modelo en esta misma máquina

make cerebro FRASE="¿hacéis lo del alisado ese?"
```

| | Claude | Ollama |
|---|---|---|
| dónde corre | en la nube | en la máquina que atiende el teléfono |
| qué sale de casa | **el texto** de lo que dijo el cliente (el audio no) | nada |
| acierta | más | menos |
| tarda | menos | más, y al teléfono se nota |
| cuesta | por llamada | la luz |

Con Ollama se le manda el mismo esquema JSON (`format`), así que la garantía
es la misma: seis campos y el servicio solo de la tabla. Se habla con él por
HTTP con `urllib`, sin cliente ni dependencia nueva, y si no está levantado la
llamada sigue con las reglas solas.

**Apagado por defecto**, y no por comodidad: cuál de los dos —o ninguno— es
una decisión del negocio. Sin nada configurado, las reglas van solas y no se
cae nada.

## La colmena: lo que trabaja cuando no suena el teléfono

Un negocio tiene cosas que pasan entre llamada y llamada y que hoy no hace
nadie. Eso son los agentes: corren **una vez al día**, dejan avisos y no
hablan con ningún cliente.

| agente | qué mira |
|---|---|
| `recordatorios` | las citas de mañana, con el mensaje listo para mandarle a cada uno |
| `resumen` | cómo viene el día: citas, huecos libres y lo previsto de la tabla |
| `huecos` | qué días de esta semana están flojos, y qué clientes repiten |
| `seguimiento` | quién lleva medio año sin venir teniendo costumbre de venir |
| `revision` | lo que está mal: tarifas sin duración, dos citas que se pisan, `frases.toml` con erratas, fichas caducadas |

```bash
make agentes-seco        # qué dirían, sin registrar nada
make agentes             # correrlos y dejar los avisos
make agentes-diarios     # que corran solos cada mañana a las 8 (timer de systemd)
```

Tres cosas que no hacen, y son a propósito:

- **No mandan nada al cliente.** `recordatorios` deja el mensaje escrito; se
  manda desde el móvil, si se quiere. Mandar SMS es otra decisión y otra
  factura, y no se toma por inercia desde un cron.
- **No deciden.** Ponen delante los números y los nombres. A quién se llama
  para llenar un hueco lo decide quien lleva el negocio.
- **Se callan cuando no hay nada.** Un agente que avisa cada mañana de que no
  hay novedades deja de leerse en una semana, y con él los que sí traían algo.

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
hace que se deje de mirar. `python3 guardado/avisos.py` los lista todos.

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
├─ telefono/     coger la llamada: entra y sale, aquí no se decide nada
│   ├─ telefonia.py     el webhook del número de verdad, una conversación por llamada
│   ├─ servidor.py      dos puertos: el privado (panel, demo) y el público (solo /telefono/*)
│   ├─ firmas.py        Ed25519 para Telnyx; el HMAC de Twilio va en telefonia
│   ├─ voz.py           la oreja (Whisper) y la boca (Piper), para la demo local
│   └─ urlpublica.py    cómo se llama esta máquina, para no imprimir huecos
│
├─ mente/        entender lo que dicen y decidir qué contestar
│   ├─ recepcion.py     quién atiende, y Conversacion: la llamada con memoria
│   ├─ rag.py           busca en los .md del negocio, en local y sin embeddings
│   ├─ cerebro.py       el LLM, opcional: entiende, no habla ni pone precios
│   ├─ conocimiento.py  tarifas y FAQ: la tabla manda, el precio es consulta
│   ├─ memoria.py       la ficha de quien llama, y su derecho a que se borre
│   └─ fechas.py        cuándo quiere la cita, siempre hacia delante
│
├─ negocio/      qué negocio es este (su personalidad vive en negocios/, no aquí)
│   ├─ negocio.py       un negocio = una carpeta
│   ├─ frases.py        lo que dice y lo que entiende, editable por negocio
│   └─ agenda.py        los huecos: reserva de verdad contra el horario
│
├─ guardado/     dónde se escribe y cómo, para que no se pierda nada
│   ├─ datos.py         la carpeta de cada bot; nadie más sabe del reparto
│   ├─ almacen.py       los JSON, con escritura atómica
│   ├─ copias.py        la copia de hoy, y restaurar sin perder lo de ahora
│   └─ avisos.py        el rastro de las llamadas, ordenado
│
├─ dueno/        lo que usa quien lleva el negocio, no quien llama
│   ├─ lanzar.py        de aquí a la primera llamada, paso a paso
│   ├─ revisar.py       ¿está listo para coger llamadas? sale 1 si no
│   ├─ panel.py         el día del dueño, en el móvil
│   ├─ aprender.py      lo que no supo contestar, para que lo escribas
│   ├─ agentes.py       la colmena: lo que trabaja cuando no suena el teléfono
│   ├─ avisar.py        los avisos, al móvil por Telegram
│   ├─ diagnostico.py   qué le pasa a esta máquina, en veinte líneas
│   └─ medir_voz.py     cuánto tarda en contestar, sin teléfono ni tarjeta
│
├─ negocios/     un bot por carpeta: tarifas.md, faq.md, negocio.toml, frases.toml
│   ├─ peluqueria/      trata de usted
│   └─ taller/          tutea, otra voz, otros servicios
│
├─ tests/        las pruebas, y tests/negocios/ con sus propios bots de mentira
└─ Makefile      instalar, lanzar, revisar, estado: un comando cada uno
```

Las carpetas son por **para qué sirve cada cosa**, no por capas técnicas. El
corte sigue las fronteras que ya había: `telefono/` no sabe qué se contesta,
`mente/` no sabe por dónde entró la llamada, y `negocios/` no tiene código.

Hay una que no se llama como parecería: `guardado/` y no `datos/`, porque
`datos/` es la carpeta de los datos de verdad y está en el `.gitignore`. Un
paquete con ese nombre no se subiría, y costaría una tarde entender por qué.


## Dónde guarda sus datos

- `GJALLARHORN_DATOS` para los avisos; `GJALLARHORN_CONOCIMIENTO` para las
  tarifas. Sin ellas, dentro del repo.
