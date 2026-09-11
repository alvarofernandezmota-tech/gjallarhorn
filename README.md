# gjallarhorn

Un recepcionista telefónico: atiende la llamada, informa de tarifas y toma la
cita. **Proyecto independiente, sin dependencias de ningún otro repo.**

> **Estado: funciona de punta a punta por texto y por voz.** Falta la telefonía
> —que una llamada de verdad entre— y eso es lo único que puede tumbarlo.

## Qué hace

```
audio → voz.escuchar → Conversacion.atender → voz.hablar → audio
                              ↓ al colgar
                        avisos.registrar
```

Una llamada normal, tal cual la atiende hoy:

```
— Buenas, ¿cuánto vale un tinte?   Tengo varias: Tinte 45 €; Corte y tinte 60 €. ¿Cuál le interesa?
— El tinte                         Tinte: 45 €, unos 90 min.
— Vale, pues quiero cita           Muy bien, una cita de tinte. ¿Qué día le viene bien?
— El jueves                        Perfecto, el jueves 17. ¿A qué hora le viene bien?
— A las cinco                      ¿Las cinco de la tarde?
— Sí                               ¿A nombre de quién se la apunto?
— Me llamo Álvaro                  Le apunto la cita de tinte el jueves 17 a las cinco
                                   de la tarde, a nombre de Álvaro. Se lo confirmamos.
```

**Recuerda.** El tinte del primer turno sigue vivo en el tercero, y «a las
cinco» —que sola no es nada— es una cita porque el día se dijo antes. Sin
memoria, esta llamada se cae en el segundo turno.

Cuatro intenciones: **precio**, **cita**, **horario** y **recado**. Y una regla
por encima de todas:

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
precio = ["cuanto", "vale", "cuesta", "precio", "me saldria"]
```

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
