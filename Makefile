VENV := .venv
ifeq ($(OS),Windows_NT)
	BIN := $(VENV)/Scripts
	PY ?= python
else
	BIN := $(VENV)/bin
	PY ?= python3.11
endif

.PHONY: setup data train eval api web test demo docker

setup:
	test -d $(VENV) || $(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -r requirements.txt
	$(BIN)/pip install -q -e . --no-deps
	test -f .env || cp .env.example .env
	cd frontend && npm install

data:
	$(BIN)/python -m agent_sim.generate

train:
	$(BIN)/python -m ml.train

eval:
	$(BIN)/python -m ml.evaluate

api:
	$(BIN)/uvicorn backend.main:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	$(BIN)/pytest

demo:
	$(MAKE) -j2 api web

docker:
	docker compose up --build
