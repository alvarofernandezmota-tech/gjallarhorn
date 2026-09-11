"""El banco de frases: contra esto se mide cualquier cerebro.

El ADR-018 deja el cerebro sin decidir —reglas, un LLM local o uno por API— y
dice que se decide **midiendo**. Esto es con qué.

Sin un banco, cualquier demo parece buena: se prueban tres frases que salen
bien y se da por bueno el modelo. Con un banco, la pregunta pasa a ser «¿cuánto
acierta, y en qué se equivoca?», que ya tiene respuesta numérica.

## Cómo leer esto

Cada entrada es **una frase y lo que debería pasar**:

    ("recuérdame llamar al dentista el jueves", "crear_tarea", "dentista")

La tercera parte es un trozo que tiene que aparecer en los argumentos. Sirve
para cazar el fallo silencioso: acertar la acción y perder la mitad de la
frase por el camino.

## Esto está para que Álvaro lo corrija

Las frases las he escrito yo imaginando cómo hablarías. **Eso es una suposición
mía, y es justo lo que no debe quedarse sin revisar**: un banco que mide contra
frases inventadas mide lo que yo creo que dices, no lo que dices.

Lo que hay que hacer con esto es hablarle al agente una semana, apuntar las
frases que falla, y meterlas aquí. Entonces el número significa algo.
"""

# (frase, acción esperada, trozo que debe salir en los argumentos)
FRASES: list[tuple[str, str, str]] = [
    # ---- al diario: lo que ha pasado, lo que siente ----
    ("apunta que hoy he dormido fatal", "apuntar_en_diario", "dormido fatal"),
    ("escribe que la reunión ha ido bien", "apuntar_en_diario", "reunión ha ido bien"),
    ("anota que me duele la espalda", "apuntar_en_diario", "duele la espalda"),
    ("para el diario: hoy he hablado con mi hermana", "apuntar_en_diario", "hermana"),
    ("apunta en el diario que he terminado el ADR", "apuntar_en_diario", "terminado el ADR"),

    # ---- tareas ----
    ("recuérdame llamar al dentista el jueves", "crear_tarea", "dentista"),
    ("recuerdame comprar pan", "crear_tarea", "comprar pan"),
    ("tengo que renovar el DNI", "crear_tarea", "renovar el DNI"),
    ("acuérdate de sacar la basura", "crear_tarea", "basura"),
    ("tarea revisar el backup de Madre", "crear_tarea", "backup"),
    ("apúntame la tarea de pagar el seguro", "crear_tarea", "seguro"),

    # ---- citas ----
    ("cita con el fisio el martes a las 10", "crear_cita", "fisio"),
    ("tengo cita en el banco mañana a las 9", "crear_cita", "banco"),
    ("ponme una cita con el dentista el viernes a las 5", "crear_cita", "dentista"),
    ("apunta una cita comida con Marta el sábado", "crear_cita", "Marta"),

    # ---- hábitos ----
    ("he hecho gimnasio", "marcar_habito", "gimnasio"),
    ("hoy he hecho yoga", "marcar_habito", "yoga"),
    ("marca lectura", "marcar_habito", "lectura"),
    ("hábito correr", "marcar_habito", "correr"),

    # ---- registro: lo que se cuenta ----
    ("registra dos cafés", "apuntar_registro", "cafés"),
    ("llevo hora y media de estudio", "apuntar_registro", "estudio"),
    ("he tomado tres cervezas", "apuntar_registro", "cervezas"),

    # ---- preguntas: NO escriben nada ----
    ("qué tengo hoy", "que_hay_hoy", ""),
    ("que hay mañana", "que_hay_hoy", ""),
    ("qué me queda por hacer", "que_hay_hoy", ""),
    ("cómo va la semana", "que_hay_hoy", ""),
    ("resumen del día", "que_hay_hoy", ""),
    ("qué toca hoy", "que_hay_hoy", ""),
    ("léeme el diario", "leer_diario", ""),
    ("lee lo de ayer", "leer_diario", ""),
    ("qué escribí el lunes", "leer_diario", ""),

    # ---- sin tildes: quien dicta no las pone, y Whisper a veces tampoco ----
    ("que tengo hoy", "que_hay_hoy", ""),
    ("recuerdame llamar a mi madre", "crear_tarea", "madre"),
    ("leeme el diario", "leer_diario", ""),

    # ---- lo que no encaja en nada: va al diario, NO se pierde ----
    ("pues no sé, el día ha sido raro", "apuntar_en_diario", "día ha sido raro"),
    ("estoy cansado", "apuntar_en_diario", "cansado"),
    ("hoy ha sido uno de esos días", "apuntar_en_diario", "uno de esos días"),
    ("qué pereza todo", "apuntar_en_diario", "pereza"),

    # ---- trampas: órdenes a medias, que no deben inventarse nada ----
    ("recuérdame", "apuntar_en_diario", "recuérdame"),
    ("apunta", "apuntar_en_diario", "apunta"),

    # ---- frases largas: lo que pasa de verdad cuando hablas ----
    ("apunta que hoy he estado toda la tarde con el bot de voz y "
     "por fin contesta algo con sentido", "apuntar_en_diario", "bot de voz"),
    ("recuérdame que mañana tengo que llamar al taller antes de las dos "
     "porque cierran", "crear_tarea", "taller"),

    # ---- ADVERSARIAS ----------------------------------------------------
    #
    # Escritas MIRANDO las reglas y buscando dónde se rompen, no escritas
    # antes. Las de arriba las aprobaba el cerebro de reglas al 100 %, que no
    # es una nota: es la señal de que el banco y la solución los ha escrito el
    # mismo. Un banco que aprueba siempre no mide nada.
    #
    # Todas estas son cosas que una persona dice de verdad.

    # La orden no va delante: primero la fecha, o el sujeto.
    ("mañana a las nueve tengo dentista", "crear_cita", "dentista"),
    ("el viernes comida con Marta", "crear_cita", "Marta"),

    # Otras formas de pedir una tarea.
    ("no se me olvide llamar a mi madre", "crear_tarea", "madre"),
    ("apúntate que tengo que ir al banco", "crear_tarea", "banco"),
    ("pon en la agenda la revisión del coche el lunes", "crear_cita", "coche"),

    # Otras formas de decir que has hecho algo.
    ("he ido al gimnasio", "marcar_habito", "gimnasio"),
    ("hoy sí he corrido", "marcar_habito", "corrido"),

    # Preguntas que no empiezan por «qué».
    ("dime qué tengo hoy", "que_hay_hoy", ""),
    ("enséñame la agenda de mañana", "que_hay_hoy", ""),
    ("qué hice ayer", "leer_diario", ""),

    # Cosas para las que NO hay acción todavía. Lo correcto no es inventarse
    # una: es que acaben en el diario sin perderse, hasta que existan.
    ("borra la tarea tres", "apuntar_en_diario", "borra la tarea tres"),
    ("cambia la cita del martes a las doce", "apuntar_en_diario", "cambia la cita"),
]


def evaluar(decidir, frases=None) -> dict:
    """Pasa un cerebro por el banco. Devuelve qué acierta y en qué falla.

    `decidir` es cualquier cosa con la firma de `cerebro.decidir`:
    `frase -> (accion, argumentos)`. Un LLM entra por aquí igual que las
    reglas, que es de lo que se trata.
    """
    frases = FRASES if frases is None else frases
    aciertos, fallos = 0, []
    for frase, esperada, trozo in frases:
        try:
            accion, argumentos = decidir(frase)
        except Exception as error:  # noqa: BLE001 — un cerebro puede reventar
            fallos.append((frase, esperada, f"reventó: {error}"))
            continue
        if accion != esperada:
            fallos.append((frase, esperada, f"dijo {accion}"))
            continue
        if trozo and trozo.lower() not in " ".join(
                str(v) for v in argumentos.values()).lower():
            # Acierta la acción y pierde la frase: el fallo que no se ve.
            fallos.append((frase, esperada, f"perdió «{trozo}» en {argumentos}"))
            continue
        aciertos += 1
    return {
        "total": len(frases),
        "aciertos": aciertos,
        "fallos": fallos,
        "acierto": aciertos / len(frases) if frases else 0.0,
    }
