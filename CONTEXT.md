# Contexto y decisiones de arquitectura

## Propósito

gjallarhorn atiende el teléfono de un negocio: coge la llamada, informa de
tarifas y toma la cita. Por voz, y en local.

## Decisiones

### 1. Proyecto independiente, sin dependencias de ningún otro repo

**Decisión**: repo propio, con sus propios `fechas.py`, `almacen.py` y
`voz.py`. No importa nada de fuera.

**Razón**: hubo unas horas en las que esto tiraba de otro repo y **se cortó a
propósito**. Un recepcionista de peluquería no tiene por qué arrastrar el repo
del diario personal de nadie para arrancar, y un fallo en un lado no puede
dejar mudo el otro. Si alguna vez hace falta algo de fuera, **se copia**: son
treinta líneas frente a una dependencia entre proyectos.

### 2. `fechas.py` mira hacia delante

**Decisión**: el parser de fechas es propio y resuelve **siempre hacia
delante**.

**Razón**: el parser de un diario hace lo contrario —«el lunes» es el lunes que
pasó— porque un diario habla del pasado. Un recepcionista es al revés: **nadie
reserva cita para el martes pasado**. Reusar uno de diario aquí era heredar
exactamente la suposición contraria a la buena.

Y no decide por su cuenta si «a las cinco» son las 17:00: devuelve `05:00` y
marca que la hora venía sin franja. Quien la confirma es el cliente,
preguntando. Es la regla que evitó citar a alguien de madrugada.

### 3. Un precio sale de la tabla o no sale

**Decisión**: el número lo pone `conocimiento.buscar()` sobre una tabla de
Markdown, no un modelo generativo. Si el servicio no está, el agente dice que
no lo sabe y toma el recado.

**Razón**: cantar un precio equivocado por teléfono cuesta dinero y
credibilidad, y ese error no se ve en las pruebas: se ve en la factura. Un LLM
podrá redactar mejor la frase, **el número no lo pone él**.

Por lo mismo esto **no es un RAG**. Con veinte servicios el conocimiento entero
cabe en el prompt y no hay paso de recuperación que pueda recuperar el trozo
equivocado. `conocimiento.cabe_en()` dirá con números cuándo deja de caber.

### 4. La voz es local

**Decisión**: Whisper para oír y Piper para hablar, los dos en la máquina de
casa. El audio no se manda a una API de terceros.

**Razón**: por ahí pasa lo que un cliente cuenta por teléfono y lo que se le
contesta. El audio original no se guarda salvo decisión explícita: es dato
personal y pesa.

### 5. Un negocio es una carpeta, palabras incluidas

**Decisión**: dar de alta un cliente es `cp -r negocios/peluqueria
negocios/otro` y editar ficheros de texto: tarifas, FAQ, saludo, y en
`frases.toml` **lo que contesta el agente y lo que entiende del cliente**. No
se toca código.

**Razón**: quien lleva el negocio tiene que poder cambiar un precio —o la
forma de despedirse, o enseñarle que en su barrio se dice «¿cuánto me
saldría?»— sin llamar a nadie. Eso solo es cierto si no hay que abrir un
`.py`.

Y como ese fichero lo edita alguien que no programa, **una errata no puede
tumbar una llamada**: se avisa al arrancar, y si se cuela, se usa la frase de
fábrica y se deja un aviso. Lo que no puede fallar no se deja en manos de que
alguien lo escriba bien. Es la misma decisión que el aviso de sistema
automático (punto 6): el saludo y los precios quedan fuera de `frases.toml` a
propósito.

### 5 bis. La llamada se recuerda

**Decisión**: `Conversacion` lleva la cuenta de la llamada entera; `atender()`
suelto queda para probar una frase.

**Razón**: quien llama no repite. «A las cinco» sola no es nada, pero es una
cita si el día se dijo dos frases antes. Y el aviso se apunta **al colgar**,
con el resultado —la cita cerrada, o lo que se quedó a medias—, no en cada
turno: cinco apuntes de los que solo el último sirve no son un registro.

### 5 ter. Reservar solo contra un horario escrito

**Decisión**: con `[horario]` en `negocio.toml`, `agenda.py` reserva —abre,
cae dentro, no se solapa— y ofrece huecos cercanos si no cabe. Sin horario,
se toma nota y se promete confirmar.

**Razón**: prometer un hueco que nadie ha comprobado es peor que no cogerlo:
el cliente se presenta y no hay sitio. Y reservar contra un horario inventado
es lo mismo con otro nombre. La única fuente de verdad es lo que el dueño
escribe; cuando no lo escribe, el agente no se lo inventa.

Solapar es pisarse en minutos, no empezar a la misma hora: un tinte de 90 min
a las 10 ocupa hasta las 11:30. Y la agenda vuelve a comprobar al reservar,
porque entre la pregunta y la reserva puede haber entrado otra llamada.

### 5 quater. El aviso se registra siempre; a Telegram va lo que no es ruido

**Decisión**: todo se apunta en `avisos.json`. A Telegram van por defecto
citas, llamadas y fallos, no las tarifas. Un aviso no se marca como visto
hasta que Telegram confirma. El envío va en un hilo aparte.

**Razón**: el registro es la verdad; el móvil es la comodidad. Perder un
aviso porque falló la red es lo peor que puede pasar aquí, así que la marca
de «visto» va detrás de la confirmación, nunca delante. Y mandar veinte
«preguntó el precio» al día es la forma segura de que se deje de mirar el
chat. El token y el chat van en `.env`, nunca en el repo: es público.

### 5 quinquies. El LLM entiende; no habla ni pone precios

**Decisión**: opcional y apagado por defecto. Entra solo cuando las reglas
no reconocen la frase, y devuelve un JSON de forma fija (intención, servicio
de la tabla o nulo, cuándo, nombre). Nunca redacta la respuesta ni pone un
número. Un servicio fuera de la tabla se descarta diga lo que diga.

**Razón**: la regla que manda es «un precio sale de la tabla o no sale», y la
forma de garantizarla con un modelo generativo en medio es que su salida no
pueda contener un precio. Y apagado por defecto porque encenderlo manda el
texto del cliente a un tercero: es una decisión del negocio, no del código.
Si falla o tarda, las reglas siguen: una llamada no se cae por un LLM.

### 6. El aviso de que es automático no se puede quitar

**Decisión**: `negocio.toml` deja personalizar el saludo, pero si el saludo
propio no dice que se habla con un sistema automático, **se le añade al
cargarlo**.

**Razón**: informar de eso no es opcional, y la única forma de garantizarlo es
que no dependa de que alguien se acuerde al editar un fichero de texto.

### 7. La telefonía va después de medir

**Decisión**: primero `medir_voz.py`, después el número de teléfono.

**Razón**: la telefonía es la parte **conocida** —un proveedor entrega la
llamada en unos cientos de milisegundos y eso no lo cambia nadie—. Lo
desconocido, y lo que puede tumbar el proyecto, es cuánto tarda Whisper en el
hardware de casa. Y eso se mide **gratis**: Piper fabrica la voz del cliente y
Whisper la escucha. Si `escuchar + pensar + hablar` no cabe holgado por debajo
de dos segundos, esta arquitectura no vale para el teléfono, y más vale
saberlo antes de pagar por un número.

**Estado (2026-09-11)**: medido. Whisper `small` tarda 2898 ms en oír 3,2 s
de audio en la máquina de casa: no cabe en el presupuesto. Decisión tomada
en consecuencia, la 7 bis.

### 7 bis. Al teléfono oye y habla el proveedor; piensa esto

**Decisión**: para el número de verdad, el proveedor transcribe y sintetiza
(`Gather input="speech"` + `Say`). Whisper y Piper se quedan para la demo del
navegador y para cuando haya una máquina que los corra en menos de un
segundo. La conversación, los precios y la agenda no salen de aquí.

**Razón**: el número lo dijo: casi tres segundos solo en oír, contra dos de
presupuesto para el turno entero. Y la privacidad del audio no cambia con
esta decisión: en cuanto hay un número, quien da la línea oye la línea. Lo
que sí es de aquí y sigue siéndolo es todo lo que se decide y se dice.

Cada petición al webhook viene firmada con el token del proveedor; sin firma
válida, 403. Sin token, el webhook no arranca. Y el webhook se publica con
`tailscale funnel`: una conexión de salida, el router intacto (decisión 8).

### 8. En el router no se abre nada

**Decisión**: para llegar desde el móvil, `tailscale serve`. No un puerto
abierto.

**Razón**: el navegador no da micrófono sin HTTPS salvo en `localhost`, así que
por IP a pelo no hay demo. `tailscale serve` da HTTPS de verdad con una
conexión **de salida**. Abrir un puerto en el router es exponer una máquina de
casa a internet a cambio de nada.

## Dónde guarda sus datos

`GJALLARHORN_DATOS` para los avisos, `GJALLARHORN_CONOCIMIENTO` para las
tarifas. Sin ellas, dentro del repo, en carpetas que están en el `.gitignore`:
esto son datos, no código.

## Estado actual

✅ **Funciona de punta a punta, por texto y por voz.** `servidor.py` levanta el
MVP en el navegador; con `--sin-voz` se prueba el recepcionista hoy, sin
instalar ningún modelo.

Medido en la máquina de casa el 2026-09-11: Piper 210 ms; **Whisper `small`
2898 ms** para 3,2 s de audio, por encima del presupuesto de 2000 ms para el
turno entero. Es un número frío (primera transcripción tras cargar).

Pendiente, por orden:

1. `make medir` y `make medir MODELO=base`: el número caliente, y el del
   modelo pequeño. Ese es el que decide.
2. Decidir la telefonía a la vista de ese número: si lo local no baja de dos
   segundos, hay que irse a una API de voz en tiempo real, que funciona mejor
   y manda el audio a un tercero.
