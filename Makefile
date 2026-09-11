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
PUERTO  ?= 8080
SERVICIO := gjallarhorn
UNIDAD   := $(HOME)/.config/systemd/user/$(SERVICIO).service

.DEFAULT_GOAL := ayuda

ayuda:  ## esta lista
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## */\t/' | column -t -s "$$(printf '\t')"

$(PY):
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip >/dev/null

instalar: $(PY)  ## venv + dependencias + modelos de voz, de una vez
	$(PIP) install faster-whisper piper-tts
	$(PY) voz.py

voz: $(PY)  ## ¿oye y habla esta maquina? versiones y milisegundos
	$(PY) voz.py

MODELO  ?= small

medir: $(PY)  ## cuanto tarda en contestar. Prueba MODELO=base y MODELO=tiny
	$(PY) medir_voz.py --negocio $(NEGOCIO) --modelo $(MODELO)

probar: $(PY)  ## el recepcionista por teclado, con memoria y agenda
	$(PY) recepcion.py --negocio $(NEGOCIO)

servidor: $(PY)  ## el MVP en primer plano (Ctrl+C para parar)
	$(PY) servidor.py --negocio $(NEGOCIO) --puerto $(PUERTO)

pruebas: $(PY)  ## las pruebas y el lint
	$(PY) -m unittest discover -s tests
	$(VENV)/bin/ruff check . 2>/dev/null || ruff check .

# ---- como servicio: arranca con la maquina, se reinicia si cae, con log ----

$(UNIDAD): gjallarhorn.service.in
	mkdir -p $(dir $(UNIDAD))
	sed -e 's|@RAIZ@|$(CURDIR)|g' -e 's|@NEGOCIO@|$(NEGOCIO)|g' -e 's|@PUERTO@|$(PUERTO)|g' \
	    gjallarhorn.service.in > $(UNIDAD)
	systemctl --user daemon-reload

arrancar: $(PY) $(UNIDAD)  ## servicio systemd: siempre encendido, se reinicia si cae
	systemctl --user enable --now $(SERVICIO)
	@echo "→ http://localhost:$(PUERTO)   (log: make log)"
	@loginctl show-user $$USER 2>/dev/null | grep -q 'Linger=yes' || \
	  echo "⚠️  para que arranque sin que inicies sesion:  sudo loginctl enable-linger $$USER"

parar:  ## parar el servicio
	systemctl --user disable --now $(SERVICIO) 2>/dev/null || true

reiniciar:  ## tras un git pull o editar el negocio
	systemctl --user restart $(SERVICIO)

log:  ## el log del servicio, en vivo
	journalctl --user -u $(SERVICIO) -f -n 50

estado: $(PY)  ## ¿vivo? ¿que modelo? ultimas citas y avisos
	@systemctl --user is-active $(SERVICIO) >/dev/null 2>&1 && echo "servicio: activo" || echo "servicio: parado"
	@$(PY) diagnostico.py --corto

diagnostico: $(PY)  ## el informe entero, para pegarlo de una vez
	@$(PY) diagnostico.py

.PHONY: ayuda instalar voz medir probar servidor pruebas arrancar parar reiniciar log estado diagnostico
