---
tipo: changelog
fecha: 2026-09-12
repo: gjallarhorn
etiquetas: [cambios, historial]
---

# Cambios

Lo que ha ido pasando, sacado del historial y no de la memoria. El repo nació
el **viernes 11 de septiembre de 2026 a las 03:42** y lleva 120 commits.

Las versiones aún no se numeran: no hay nada desplegado de cara al público.
Cuando entre la primera llamada de verdad, eso será la `0.1.0`.

---

## Sin publicar — sábado 12 de septiembre

Hecho y en verde en local; **todavía no está en GitHub**.

### El cerebro sale a su propio repositorio

`mente/`, `negocio/` y `guardado/` se van a
[hugin](https://github.com/alvarofernandezmota-tech/hugin) y vuelven montados
como submódulo en `hugin/`. Aquí se quedan `telefono/` y `dueno/`.

Una llamada, un chat y una ventana web son la misma conversación vista por
sitios distintos, y lo que decide qué contestar no tiene por qué enterarse de
cuál es. Eso llevaba escrito en el README desde el primer día; ahora es una
frontera con pruebas a los dos lados, no una buena intención.

Antes del corte hubo que romper dos dependencias que iban en el sentido
contrario sin que nadie lo hubiera decidido:

- `mente/recepcion.py` importaba `telefono/voz.py` solo por su `main()` de
  pruebas — se movió a `telefono/demo.py`.
- `mente/cerebro.py` importaba `dueno/avisar.py` **entero** para preguntarle
  si había una clave de LLM puesta — la lectura del `.env` salió a
  `guardado/ajustes.py`.

**El fallo que casi se cuela:** tres funciones resolvían carpetas de datos con
`Path(__file__).parent.parent`. Eso apuntaba bien mientras el código vivía
dentro de la aplicación, y apunta **dentro del submódulo** en cuanto sale a
librería: la agenda, el conocimiento y los datos de clientes se habrían
escrito en una carpeta que no es de nadie, con el bot contestando tan
tranquilo que no hay citas. Ahora salen del directorio de trabajo, y hay una
prueba en hugin que lee el árbol de sintaxis y no deja que vuelva a aparecer
un `__file__`.

### Lo demás del día

- **SignalWire como tercer proveedor**, sin criptografía nueva: firma igual
  que Twilio, así que es la misma comprobación.
- **La suite leía tu `.env`** y fallaba en la máquina que ya tenía el bot
  configurado y pasaba en un portátil recién clonado. La causa: la ruta del
  `.env` estaba en un argumento por defecto, que Python evalúa una vez al
  definir la función.
- `apuntar_nota()` **no tenía ni una prueba** — la escribe el dueño, no el
  cliente, así que ninguna conversación la ejercitaba.
- Fuera el andamio vacío: `scripts/` y `docs/procedimientos/` eran dos
  carpetas con un único README cuyo índice decía «vacío», y la de `scripts/`
  además describía una estructura que ya era imposible.
- Las cinco plantillas de systemd, sueltas en la raíz, pasan a `systemd/`.

---

## Viernes 11 de septiembre — de cero a hablar por teléfono

109 commits en un día. Lo que se construyó, por orden:

### El agente

- La estructura base, el banco de frases y los avisos de las llamadas.
- **Lo que el agente sabe del negocio, sin montar un RAG**: la tabla manda y
  el precio sale de ahí o no sale.
- **Un negocio es una carpeta.** Dar de alta un cliente no toca código, y eso
  incluye las palabras: `frases.toml`.
- **La llamada se recuerda**, que es lo que la convierte en conversación.
- **La agenda**, que es lo que convierte «tomo nota» en «reservada»: reserva
  de verdad contra el horario escrito.
- **El RAG, en local y sin embeddings**: cualquier `.md` del negocio contesta.
- **Memoria de quien llama**: lo de siempre, su franja habitual, y el derecho
  a que se borre.
- **El LLM, opcional**, solo donde las reglas no llegan y **sin poner
  precios**: devuelve datos con forma fija, no frases.
- **La colmena**: los agentes que trabajan cuando no suena el teléfono.
- **El panel del dueño**: abrir el móvil y ver cómo va el día.
- **El bot dice qué le preguntan y no sabe contestar**, para que se escriba.

### La voz y el teléfono

- El bucle de voz cerrado, y el MVP hablando desde el navegador.
- **El teléfono de verdad, a un token de distancia**: el webhook, con firma.
- **Telnyx**, que no firma como Twilio: Ed25519 escrito a mano y validado
  contra los vectores oficiales del RFC 8032.
- **`make lanzar`**: de un repo clonado a la primera llamada, paso a paso.
- **`make revisar`**: una orden que dice si el bot está listo para llamadas y
  sale con 1 si no.
- **Lo que sale a internet es un puerto aparte, no una ruta aparte.**

### Los fallos que costaron más de encontrar

Estos son los que enseñan algo:

| Qué pasaba | Por qué era grave |
|---|---|
| **Un `.env` con una línea de más dejaba el teléfono muerto y todo en verde** | Python se quedaba con la primera clave repetida y systemd con la última. `revisar` veía una credencial y el servicio arrancaba con otra |
| **Piper no escribía la cabecera del WAV, y el error no lo decía** | El audio salía y no sonaba |
| **La llamada desde el iPhone no habría funcionado** | Se descubrió antes de que pasara |
| **Un `frases.toml` roto tumbaba la llamada** | Justo lo contrario de lo que el repo prometía: una errata en un fichero editable no puede tirar una llamada |
| **Se confundía el Account SID de Twilio con el Auth Token** | Los dos son cadenas largas; con el equivocado, 403 en todas las llamadas |
| **`make lanzar` guardaba el token en el paso 1 y el paso 3 no lo leía** | Se configuraba bien y salía mal |
| **Las pruebas se cambiaban los datos entre ellas** | Solo fallaba al correr la suite entera, que es la peor forma de descubrirlo |

### Y los de conversación, que son los que se oyen por teléfono

- «para mi hija» es el corte infantil aunque se hablara de otro corte.
- «sí, a las seis» tras ofrecer un hueco es **las seis**, no el hueco ofrecido.
- «mañana por la mañana» es el día siguiente, y el horario no se lee como un reloj.
- Preguntar de qué es la cita **una vez**, antes de ofrecer huecos.
- Nombrar un servicio no es pedirlo; y cambiar de idea a mitad se entiende.
- Pedir hora sin decir «cita», y dar el nombre de otra persona.
- «lo que sea» no es un nombre.
- Anular una cita ya no reserva otra, y no se cita en el pasado.

---

## Lo que se sabe que falta

- **«¿se puede ir sin cita?» contesta la política de anulación.** El título de
  la respuesta buena («¿Hace falta cita?») se reduce a una sola palabra al
  quitar las vacías, y pierde contra otra que comparte «ir» y «cita». El
  cuerpo correcto dice literalmente «se puede pasar sin cita» y pesa poco.
- **«¿cuánto se tarda en un corte?» dice que no tiene ese servicio**, y sí lo
  tiene: son tres cuartos de hora.
- No hay `LICENSE`, ni `SECURITY.md`, ni CI.
- `dueno/medir_voz.py` no tiene pruebas.
