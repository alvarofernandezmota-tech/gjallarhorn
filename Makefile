# Operar gjallarhorn con un comando. `make` a secas lista lo que hay.
#
# Todo pasa por el .venv del repo: en Arch y Debian el pip del sistema esta
# bloqueado (externally-managed) y un `pip install` a pelo acaba donde el
# interprete que falla no mira. Es la causa numero uno de «lo instale y dice
# que falta», y esto la quita de en medio.

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
NEGOCIO ?= peluqueria
# Dos puertos, y la diferencia importa: el de la demo NO se publica nunca
# —sirve la pagina, /hablar y /colgar—; el del telefono sirve solo el webhook
# del proveedor y es el unico que sale a internet.
PUERTO  ?= 8080
PUERTO_TELEFONO ?= 8081
SERVICIO := gjallarhorn
UNIDAD   := $(HOME)/.config/systemd/user/$(SERVICIO).service

.DEFAULT_GOAL := ayuda

ayuda:  ## esta lista
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## */\t/' | column -t -s "$$(printf '\t')"

$(PY):
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip >/dev/null

instalar: $(PY)  ## venv + dependencias + modelos de voz, de una vez
	$(PIP) install faster-whisper piper-tts anthropic
	$(PY) voz.py

voz: $(PY)  ## ¿oye y habla esta maquina? versiones y milisegundos
	$(PY) voz.py

MODELO  ?= small

medir: $(PY)  ## cuanto tarda en contestar. Prueba MODELO=base y MODELO=tiny
	$(PY) medir_voz.py --negocio $(NEGOCIO) --modelo $(MODELO)

probar: $(PY)  ## el recepcionista por teclado, con memoria y agenda
	$(PY) recepcion.py --negocio $(NEGOCIO)

servidor: $(PY)  ## el MVP en primer plano (Ctrl+C para parar)
	$(PY) servidor.py --negocio $(NEGOCIO) --puerto $(PUERTO) --puerto-telefono $(PUERTO_TELEFONO)

serve: $(PY)  ## la demo, visible solo en tu tailnet (para el movil)
	tailscale serve --bg $(PUERTO)
	@tailscale serve status

cerebro: $(PY)  ## ¿que entiende el LLM de una frase? (FRASE="...")
	$(PY) cerebro.py "$(FRASE)" --negocio $(NEGOCIO)

funnel: $(PY)  ## publicar SOLO el webhook del telefono en internet
	@$(PY) -c "import telefonia, sys; sys.exit(0 if telefonia.configuracion() else 1)" || \
	  { echo "❌ sin GJALLARHORN_TELEFONO_TOKEN en .env no hay webhook que publicar."; \
	    echo "   Publicar esto ahora solo abriria la demo a internet. Pon el token primero."; \
	    exit 1; }
	tailscale funnel --bg $(PUERTO_TELEFONO)
	@echo
	@echo "Se ha publicado el puerto $(PUERTO_TELEFONO), que sirve SOLO /telefono/*."
	@echo "El $(PUERTO) (la pagina, /hablar, /colgar) sigue sin salir de tu tailnet."
	@echo
	@echo "→ en el proveedor, webhook de voz:  https://<esta-maquina>.<tailnet>.ts.net/telefono/entrada"
	@echo "  y status callback:                https://<esta-maquina>.<tailnet>.ts.net/telefono/fin"

sin-funnel:  ## dejar de publicar: nada sale a internet
	tailscale funnel --https=443 off
	@tailscale funnel status 2>/dev/null || true

avisar: $(PY)  ## mandar al movil los avisos pendientes (Telegram)
	$(PY) avisar.py

telegram-prueba: $(PY)  ## ¿llega un mensaje al movil? comprueba token y chat
	$(PY) avisar.py --prueba

pruebas: $(PY)  ## las pruebas y el lint
	$(PY) -m unittest discover -s tests
	$(VENV)/bin/ruff check . 2>/dev/null || ruff check .

# ---- como servicio: arranca con la maquina, se reinicia si cae, con log ----

$(UNIDAD): gjallarhorn.service.in
	mkdir -p $(dir $(UNIDAD))
	sed -e 's|@RAIZ@|$(CURDIR)|g' -e 's|@NEGOCIO@|$(NEGOCIO)|g' -e 's|@PUERTO@|$(PUERTO)|g' \
	    -e 's|@PUERTO_TELEFONO@|$(PUERTO_TELEFONO)|g' \
	    gjallarhorn.service.in > $(UNIDAD)
	systemctl --user daemon-reload

arrancar: $(PY) $(UNIDAD)  ## servicio systemd: siempre encendido, se reinicia si cae
	systemctl --user enable --now $(SERVICIO)
	@echo "→ http://localhost:$(PUERTO)   (log: make log)"
	@loginctl show-user $$USER 2>/dev/null | grep -q 'Linger=yes' || \
	  echo "⚠️  para que arranque sin que inicies sesion:  sudo loginctl enable-linger $$USER"

TIMER := $(HOME)/.config/systemd/user/gjallarhorn-actualizar.timer
ACTUALIZAR := $(HOME)/.config/systemd/user/gjallarhorn-actualizar.service

$(ACTUALIZAR): gjallarhorn-actualizar.service.in
	mkdir -p $(dir $(ACTUALIZAR))
	sed -e 's|@RAIZ@|$(CURDIR)|g' gjallarhorn-actualizar.service.in > $(ACTUALIZAR)
	systemctl --user daemon-reload

$(TIMER): gjallarhorn-actualizar.timer.in
	mkdir -p $(dir $(TIMER))
	cp gjallarhorn-actualizar.timer.in $(TIMER)
	systemctl --user daemon-reload

auto: $(ACTUALIZAR) $(TIMER)  ## que Madre se actualice sola: git pull cada 5 min y reinicia si cambio
	systemctl --user enable --now gjallarhorn-actualizar.timer
	@echo "→ cada 5 minutos: git pull --ff-only; si hay commits nuevos, make reiniciar."
	@echo "  Con esto, fusionar en GitHub basta. Ver: systemctl --user list-timers"

sin-auto:  ## dejar de actualizar sola
	systemctl --user disable --now gjallarhorn-actualizar.timer 2>/dev/null || true

parar:  ## parar el servicio
	systemctl --user disable --now $(SERVICIO) 2>/dev/null || true

# Depende de la unidad a proposito: un `git pull` puede traer una plantilla
# nueva —puertos, argumentos— y reiniciar sin regenerarla deja el servicio
# arrancando con los argumentos viejos, sin decirlo. Make ya sabe si hay que
# rehacerla: si no ha cambiado, esto no hace nada.
reiniciar: $(UNIDAD)  ## tras un git pull o editar el negocio
	systemctl --user restart $(SERVICIO)

log:  ## el log del servicio, en vivo
	journalctl --user -u $(SERVICIO) -f -n 50

estado: $(PY)  ## ¿vivo? ¿que modelo? ultimas citas y avisos
	@systemctl --user is-active $(SERVICIO) >/dev/null 2>&1 && echo "servicio: activo" || echo "servicio: parado"
	@test -f $(UNIDAD) -a gjallarhorn.service.in -nt $(UNIDAD) && \
	  echo "⚠️  la unidad de systemd se quedo atras: make reiniciar" || true
	@$(PY) diagnostico.py --corto

diagnostico: $(PY)  ## el informe entero, para pegarlo de una vez
	@$(PY) diagnostico.py

.PHONY: ayuda instalar voz medir probar servidor serve pruebas cerebro funnel sin-funnel auto sin-auto avisar telegram-prueba arrancar parar reiniciar log estado diagnostico
