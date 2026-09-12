---
tipo: changelog
fecha: 2026-09-12
repo: hugin
etiquetas: [cambios, historial]
---

# Cambios

El repo nació el **2026-09-12**, sacado de
[gjallarhorn](https://github.com/alvarofernandezmota-tech/gjallarhorn). La
historia anterior de estos ficheros está allí: 109 commits del 2026-09-11.

Sin versiones numeradas todavía: no hay nada desplegado de cara al público.

---

## 2026-09-12 — el corte

### Nace el repo

`mente/`, `negocio/` y `guardado/` salen de gjallarhorn. El corte estaba
**medido, no supuesto**: los tres paquetes solo se importaban entre ellos.

Antes hubo que romper dos dependencias que iban al revés sin que nadie lo
hubiera decidido: `recepcion.py` importaba `telefono/voz.py` por su `main()`
de pruebas, y `cerebro.py` importaba `dueno/avisar.py` entero solo para
preguntar si había una clave de LLM puesta.

### Las carpetas de la aplicación no salen de `__file__`

**El fallo que casi se cuela.** `Path(__file__).parent.parent / "datos"`
apuntaba a la raíz del repo mientras esto vivía dentro de la aplicación.
Sacado a librería apunta **aquí dentro**: la agenda, el conocimiento y los
negocios se habrían escrito dentro del submódulo —datos de clientes en una
carpeta que no es de nadie— y el bot habría seguido diciendo que no hay citas.

Los tres se resuelven desde el directorio de trabajo. La prueba que lo sujeta
lee el árbol de sintaxis y no el texto: los comentarios de aquí **explican**
por qué no se usa `__file__`, y buscando la cadena a pelo saltaría la propia
documentación de la regla.

### `apuntar_nota()` no tenía ni una prueba

La escribe el dueño, no el cliente, así que ninguna conversación la
ejercitaba. En una auditoría salía como función muerta; no lo está, estaba
sin red. Seis pruebas.

### Dos preguntas que se contestaban mal con toda seguridad

Salieron metiendo llamadas de verdad en lote, no leyendo código.

**«¿Cuánto tarda un corte?» decía «no tengo ese servicio»**, teniendo cuatro.
Una sola palabra: «cuesta» es palabra vacía y se tira, «tarda» no, así que
`buscar()` exigía encontrar «tarda» en el nombre del servicio. Los verbos de
duración pasan a ser relleno.

**«¿Se puede ir sin cita?» contestaba la política de anulación.** Medido: la
pregunta son tres palabras —ir (idf 1.99), sin (1.48), cita (0.69)— y el
título equivocado comparte las dos que más pesan. El título bueno, «¿Hace
falta cita?», se queda en una palabra al quitar las vacías y pesa un 75%.

Lo que las separa es que **«sin cita» sale tal cual, palabra tras palabra**.
Se añadió la señal de pares consecutivos: 0.30 → 0.47, y adelanta a la mala
(0.43). Todavía no gana por el margen que exige `VENTAJA`, así que toma recado
en vez de contestar otra cosa —que ya es mejor— pero el orden es el correcto.

---

## Lo que se sabe que falta

- **«¿Tenéis algo sin gluten?» abre una cita.** «tenéis algo» está en el
  intento de disponibilidad. El arreglo se intentó, **rompió una prueba
  legítima** («¿tenéis algo el jueves por la mañana?» sí es disponibilidad) y
  se revirtió. Necesita un arreglo mejor pensado.
- «¿Se puede ir sin cita?» ordena bien pero no supera el margen de `VENTAJA`.
- No hay `LICENSE` ni `SECURITY.md`.
