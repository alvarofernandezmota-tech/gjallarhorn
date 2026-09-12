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

### «Quiero encargar una tarta» no encontraba ninguna tarta

La frase con la que empieza casi cualquier llamada de encargo. Medido, y la
causa es de fondo: **`buscar()` intersecta** — exige que cada palabra
significativa esté en el nombre del servicio, así que una sola que no esté en
ninguno vacía el resultado entero.

```
'tarta'                → 4 servicios
'encargar una tarta'   → 0            ← un verbo de más
```

Parcheado metiendo los verbos de encargar en la lista de relleno. **Es la
segunda vez hoy que se arregla el mismo síntoma** —la primera fue con
«tarda»— y eso ya dice lo que hay: mientras `buscar()` intersecte, la lista de
palabras vacías nunca va a estar completa.

---

## Lo que se sabe que falta

### `buscar()` intersecta, y esa es la deuda de verdad

Dos fallos del mismo día tuvieron la misma causa y los dos se arreglaron
añadiendo palabras a una lista. **La tercera vez toca cambiar la función**:
que ordene por cuántas palabras encajan en vez de exigirlas todas. Mientras
tanto, cualquier verbo que a alguien se le ocurra y no esté en la lista deja
al bot diciendo «no tengo ese servicio» de algo que sí tiene.

### La FAQ que nombra el catálogo entero gana a la tabla

«Quiero encargar unos cupcakes» y «¿cuántas raciones tiene la mediana?» se
llevan la respuesta de la antelación, porque su cuerpo nombra tartas,
galletas, cupcakes, bombones y mesas dulces. Es exactamente el riesgo del que
avisa el comentario de `PESO_TITULO`, visto desde el otro lado: allí el
peligro era que un bloque que nombra medio catálogo se llevara las preguntas
de precio; aquí se las lleva igual porque el peso del título no basta cuando
el título se queda en una palabra.


- **«¿Tenéis algo sin gluten?» abre una cita.** «tenéis algo» está en el
  intento de disponibilidad. El arreglo se intentó, **rompió una prueba
  legítima** («¿tenéis algo el jueves por la mañana?» sí es disponibilidad) y
  se revirtió. Necesita un arreglo mejor pensado.
- «¿Se puede ir sin cita?» ordena bien pero no supera el margen de `VENTAJA`.
- No hay `LICENSE` ni `SECURITY.md`.
