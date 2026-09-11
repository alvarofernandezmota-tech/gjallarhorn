# Instrucciones para agentes IA

## Lo primero: este repo es PÚBLICO

Comprobado contra la API el 2026-09-11: `private: false`. Nada de lo que se
escriba aquí puede llevar **IPs, nombres de host con dirección, rutas a
claves, tokens ni contenido de repos privados**. Si hace falta un ejemplo de
dirección, va un marcador (`IP_DE_TU_MAQUINA`), no la de verdad.

Ya ha pasado una vez en la cuenta: una clave de OpenRouter vivió meses en el
historial público de `ai-toolkit`. Quitarla del árbol no la quita del
historial.

## Qué es gjallarhorn

Un **recepcionista telefónico**: coge la llamada, informa de tarifas y toma la
cita. Por voz, y en local.

```
audio → voz.escuchar → recepcion.atender → voz.hablar → audio
                             ↓
                       avisos.registrar
```

Las decisiones y sus porqués: [`CONTEXT.md`](CONTEXT.md). Cómo se usa:
[`README.md`](README.md).

## Independiente: no importa ningún otro repo

`fechas.py`, `almacen.py` y `voz.py` son propios. Hubo unas horas en las que
esto tiraba de otro repo y **se cortó a propósito**: un recepcionista de
peluquería no tiene por qué arrastrar el repo del diario personal de nadie
para arrancar.

Si alguna vez hace falta algo de otro repo, **cópialo aquí**. Son treinta
líneas frente a una dependencia entre proyectos. Y ojo con copiar de un
diario: un parser de fechas de diario resuelve hacia **atrás**, que es justo
lo contrario de lo que necesita una cita.

## Estado actual

✅ **De punta a punta, por voz, desde un móvil.** Conversación con memoria,
agenda que reserva contra el horario, avisos al móvil por Telegram, y todo
se opera con `make`. 220 pruebas, `ruff` limpio. Verificado en la máquina de
casa el 2026-09-11: una llamada por voz desde un iPhone, oída y contestada.

⚠️ Lo que **no** está hecho, y conviene no leerlo al revés:

- **La latencia está medida y no llega.** Whisper `small` en esa máquina:
  2898 ms para 3,2 s de audio, contra un presupuesto de 2000 ms para el turno
  entero. Es un número frío; `make medir` da el caliente y `MODELO=base` el del
  modelo pequeño. Hasta tener esos dos, no se decide nada.
- **El teléfono está a un token de distancia.** El webhook (`telefonia.py`)
  existe y está probado; falta un número en un proveedor TwiML y su token en
  `.env`. Al teléfono oye y habla el proveedor —Whisper no llega a tiempo—;
  la conversación, los precios y la agenda siguen siendo de aquí.
- **El LLM está apagado por defecto.** Con `ANTHROPIC_API_KEY` en `.env`
  entra donde las reglas no llegan, y devuelve datos, no frases ni precios.
  Encenderlo manda el texto del cliente a la API: lo decide el negocio.

## Reglas de la casa

- **Un precio sale de la tabla o no sale.** Nunca aproximado, nunca una
  horquilla. Si el servicio no está: no lo sé, y se toma el recado.
- **Una hora sin acotar se pregunta.** «A las cinco» no se convierte en las
  17:00 por su cuenta.
- **El audio no sale de casa.** Whisper y Piper en local. El audio original no
  se guarda salvo decisión explícita, y el `.gitignore` ya lo excluye.
- **Un negocio es una carpeta.** Dar de alta un cliente no toca código, y
  eso incluye las palabras: `frases.toml`. El saludo y los precios quedan
  fuera de ahí a propósito.
- **Una errata en un fichero editable no tumba una llamada.** Se avisa al
  arrancar; si se cuela, frase de fábrica y aviso.
- **Procedimiento ↔ script con el mismo nombre base** — la regla de la casa:
  `docs/procedimientos/algo.md` ↔ `scripts/algo.py`.
- **Commits**: `tipo: descripción breve en presente` (feat, fix, docs, chore,
  refactor, test). Un commit por cambio lógico.
- **Trabajo no trivial**: rama corta y PR en borrador.

## Verificación

```bash
make pruebas          # unittest + ruff, con el python del .venv
```

O a mano: `python3 -m unittest discover -s tests` y `ruff check .`, desde la
raíz. **Una comprobación saltada no es una comprobación pasada.**

La CI de la cuenta **no arranca** desde el 2026-09-04 por un cobro rechazado:
las ejecuciones salen en rojo en segundos, sin coger runner y con los logs en
404. Un check en rojo en GitHub no dice nada del código. Mientras siga así,
estas dos órdenes en local son la única verificación real.

## Lo que NO hay que hacer aquí

- Dar un precio que no esté en la tabla.
- Confirmar una hora que el cliente no acotó.
- Mandar audio a una API de terceros, por cómodo que sea.
- Quitar el aviso de que se habla con un sistema automático.
- Importar otro repo en vez de copiar las treinta líneas que hagan falta.
- Abrir un puerto en el router para enseñar la demo.
- Empezar la telefonía antes de haber medido la latencia.
- Dar nada por bueno sin correr las pruebas y `ruff`.
- Meter el token de Telegram, una IP o un nombre de máquina en el repo. Van en
  `.env` o no van.
- Marcar un aviso como visto antes de que Telegram confirme que lo tiene.
- Dejar que el LLM redacte lo que se le dice al cliente, o ponga un precio.
  Su salida es un JSON de cuatro campos, y así se queda.
- Atender una petición del webhook de teléfono sin comprobar la firma.
- Poner una ruta nueva en el puerto del teléfono (el público). Ahí solo vive
  `/telefono/*`; todo lo demás va en el de la demo, que no sale del tailnet.
