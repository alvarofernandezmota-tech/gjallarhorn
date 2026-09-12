# hugin

**El cerebro de un bot que atiende a gente.** Entiende lo que le dicen,
decide qué contestar y guarda lo que hay que guardar. **No sabe por dónde le
hablan.**

Librería. No se arranca, no escucha en ningún puerto, no tiene servicio. Solo
biblioteca estándar; `anthropic` es opcional y solo para el LLM.

De los dos cuervos de Odín —Hugin el pensamiento, Munin la memoria— este es el
que piensa.

## La regla que justifica que este repo exista

**Aquí no entra ni un import de un canal.** Una llamada de teléfono, un chat y
una ventana web son la misma conversación vista por sitios distintos: entra
texto, sale texto.

Si un módulo de aquí necesita saber que hay un teléfono al otro lado, **el
corte está mal hecho y lo que hay que mover es la decisión, no el import**.

No es un buen propósito: `tests/test_libreria.py` lee el **árbol de sintaxis**
de cada módulo y se cae si aparece `telefono`, `dueno`, `twilio`, `telnyx`,
`signalwire` o `flask`.

## Las reglas del dominio

Romper cualquiera de estas cuesta dinero o credibilidad en una llamada real.

- **Un precio sale de la tabla o no sale.** Lo pone `conocimiento.buscar()`
  sobre un Markdown. Un LLM puede redactar mejor la frase; **el número no lo
  pone él**. Si el servicio no está, se dice que no se sabe.
- **Se reserva contra el horario escrito o no se reserva.** Sin `[horario]`,
  se toma nota; no se inventa un hueco.
- **Una hora sin franja no se supone.** «a las cinco» devuelve `05:00` y la
  marca de que venía sin franja. Quien la confirma es el cliente. Es la regla
  que evitó citar a alguien de madrugada.
- **Las fechas van siempre hacia delante.** Nadie reserva para el martes
  pasado. Un parser de diario resuelve al revés: no se reutiliza.
- **Un hueco ofrecido tiene que poder cogerse.** Si `huecos()` lo ofrece,
  `reservar()` no puede rechazarlo por «pasado».
- **El derecho al olvido borra de verdad.** `olvidar()` no marca un
  `borrado = true`: quita la ficha. Las citas futuras se quedan, que son del
  negocio.

## Invariantes del código

- **Nada de `__file__` para rutas de datos.** Esta librería vive **dentro** de
  la aplicación que la usa: `__file__` apunta aquí, no a la raíz de quien
  despliega. Se resuelve desde el directorio de trabajo. Hay prueba que lo
  sujeta, y lee el árbol de sintaxis porque los comentarios que explican la
  regla contienen la palabra.
- **El `.env` se lee con la última clave ganando**, como `EnvironmentFile=` de
  systemd. Al revés, la verificación ve una credencial y el servicio arranca
  con otra.
- **El repositorio ES el paquete.** La carpeta se llama `hugin` y lo que la
  contiene está en el `sys.path`. Los imports de casa son `hugin.mente`, nunca
  `mente` a secas: lo segundo funciona al correr las pruebas desde la raíz y
  se cae montado como submódulo, que es donde de verdad se usa.

## Estructura

- `mente/` — `recepcion.py` quién atiende, y `Conversacion`, la llamada con
  memoria · `rag.py` busca en los `.md` del negocio, local y sin embeddings ·
  `cerebro.py` el LLM opcional · `conocimiento.py` tarifas y FAQ ·
  `memoria.py` la ficha de quien llama · `fechas.py`.
- `negocio/` — `negocio.py` un negocio es una carpeta · `frases.py` lo que
  dice y lo que entiende, editable · `agenda.py` los huecos de verdad.
- `guardado/` — `ajustes.py` el `.env` · `datos.py` la carpeta de cada bot ·
  `almacen.py` JSON atómico · `copias.py` · `avisos.py`.
- `tests/` — y `tests/negocios/` con sus propios negocios de mentira.

## Verificar

```bash
make pruebas     # 356 pruebas y el lint
```

## Commits

`tipo: descripción breve en presente` (feat, fix, docs, chore, refactor,
test). Un commit por cambio lógico.
