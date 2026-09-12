# gjallarhorn

**Un bot de voz para citas.** Coge el teléfono de un negocio, informa de
tarifas y reserva la cita. En español, y sin que nadie tenga que tocar código
para dar de alta un cliente nuevo.

Solo biblioteca estándar en el camino de la llamada. Python 3.11+.

## Dos repositorios, y la dependencia va en un solo sentido

- **Aquí**: por dónde entra la conversación (`telefono/`) y quién la opera (`dueno/`).
- **`hugin/`** (submódulo): qué se contesta — `mente/`, `negocio/`, `guardado/`.

`gjallarhorn` usa el cerebro; **el cerebro no sabe que existe un teléfono**.
Si escribes aquí `from mente import ...`, es `from hugin.mente import ...`. Si
te ves metiendo `from telefono import ...` dentro de `hugin/`, para: lo que
hay que mover es la decisión, no el import. Las dos cosas tienen prueba y
tumban el build.

## Las reglas del dominio

Estas no son preferencias de estilo. Romper cualquiera cuesta dinero o
credibilidad en una llamada real.

- **Un precio sale de la tabla o no sale.** Lo pone `conocimiento.buscar()`
  sobre un Markdown. Un LLM puede redactar mejor la frase; **el número no lo
  pone él**. Si el servicio no está, se dice que no se sabe y se toma recado.
- **El aviso de que es automático no se puede quitar.** Al cargar el saludo se
  comprueba, y si no lo dice **se le añade**. No es un descuido que se pueda
  cometer editando un fichero.
- **Se reserva contra el horario escrito o no se reserva.** Sin `[horario]` en
  el `negocio.toml`, el bot toma nota; no inventa un hueco.
- **Una hora sin franja no se supone.** «a las cinco» devuelve `05:00` y una
  marca de que venía sin franja. Quien la confirma es el cliente. Es la regla
  que evitó citar a alguien de madrugada.
- **Las fechas van siempre hacia delante.** Nadie reserva para el martes
  pasado. Un parser de diario resuelve al revés: no se reutiliza.
- **Un hueco ofrecido tiene que poder cogerse.** Si `huecos()` lo ofrece,
  `reservar()` no puede rechazarlo por «pasado».
- **Una errata en un fichero editable no tumba una llamada.** Se avisa al
  arrancar; si se cuela, frase de fábrica y aviso.
- **El audio de los clientes no se versiona nunca.** Está en el `.gitignore`.

## Invariantes del código

- **Nada de `__file__` para rutas de datos en `hugin/`.** Esa librería vive
  dentro de la aplicación que la usa: `__file__` apunta al submódulo, no a la
  raíz. Se resuelve desde el directorio de trabajo, que las unidades de
  systemd fijan. Hay prueba que lo sujeta.
- **El `.env` se lee con la última clave ganando**, como `EnvironmentFile=` de
  systemd. Al revés, `revisar` ve una credencial y el servicio arranca con
  otra, y eso no se ve por ningún lado.
- **Dos puertos, y la diferencia es de seguridad.** El privado (8080) sirve
  panel y demo y **no sale a internet nunca**; el público (8081) solo sirve
  `/telefono/*`.
- **Sin con qué comprobar la firma, el webhook no arranca.** Un teléfono que
  atiende a cualquiera que sepa la URL no es un teléfono.
- **Cada llamada es su propia conversación.** Pueden entrar dos a la vez.
- Las pruebas **no leen tu `.env`** ni escriben en tus datos. Si una prueba se
  comporta distinto según lo que tengas configurado, no dice nada.

## Estructura

- `telefono/` — `telefonia.py` el webhook del número de verdad · `servidor.py`
  los dos puertos · `firmas.py` Ed25519 para Telnyx (el HMAC de Twilio va en
  telefonia) · `voz.py` Whisper y Piper para la demo local · `demo.py` hablar
  por teclado · `urlpublica.py`.
- `dueno/` — `lanzar.py` de cero a la primera llamada · `revisar.py` ¿está
  listo? sale 1 si no · `panel.py` · `aprender.py` · `agentes.py` · `avisar.py`
  Telegram · `diagnostico.py` · `medir_voz.py`.
- `hugin/` — el submódulo con el cerebro. Tiene su propio CLAUDE.md.
- `negocios/` — un bot por carpeta: `negocio.toml`, `tarifas.md`, `faq.md`,
  `frases.toml`. **Aquí no hay código.**
- `systemd/` — las plantillas de las unidades; `make` las rellena.
- `tests/` — y `tests/negocios/` con sus propios bots de mentira.

## Verificar

```bash
make pruebas     # las de aquí y las de hugin, y el lint
```

Corre las dos suites y **falla si el submódulo está vacío**. Una comprobación
saltada no es una comprobación pasada. No hay otra verificación real: la CI de
la cuenta no arranca.

## Commits

`tipo: descripción breve en presente` (feat, fix, docs, chore, refactor,
test). Un commit por cambio lógico. Trabajo no trivial: rama corta y PR.
