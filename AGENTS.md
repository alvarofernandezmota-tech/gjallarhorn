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

✅ **De punta a punta, por texto y por voz.** `servidor.py` levanta el MVP en el
navegador. 119 pruebas, `ruff` limpio.

⚠️ Dos cosas que **no** están hechas, y conviene no leerlas al revés:

- **La latencia no está medida.** `voz.Whisper` y `voz.Piper` están escritos y
  probados contra fakes, pero nadie ha cronometrado un turno de verdad. Eso lo
  hace `medir_voz.py` en la máquina donde vaya a correr, y hasta entonces
  «tarda poco» es una suposición.
- **No hay telefonía.** Entra voz y sale voz por el navegador; lo que no hay es
  una línea. Esa decisión se toma con el número de `medir_voz.py` delante.

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
python3 -m unittest discover -s tests
ruff check .
```

Las dos, desde la raíz del repo, y **una comprobación saltada no es una
comprobación pasada**.

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
