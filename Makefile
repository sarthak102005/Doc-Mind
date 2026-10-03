# DocMind Makefile. Works with GNU make on Linux/macOS and on Windows
# (recipes avoid shell-specific syntax so they also run under cmd.exe).
#
#   make up      start postgres, qdrant, redis, minio (dev infra only)
#   make api     run the FastAPI backend natively (http://127.0.0.1:8000)
#   make test    unit tests (+ integration tests when infra is up: make test-all)
#   make lint    ruff + mypy
#   make eval    golden-question evaluation (Phase 8)
#   make bench   ingestion/latency benchmark (Phase 8)
#   make doctor  RAM + settings sanity check

UV      ?= python -m uv
COMPOSE ?= docker compose
BACKEND := backend

.PHONY: help env setup up down ps logs full-up full-down api worker test test-all lint fmt typecheck eval bench doctor health

help:
	@echo Targets: env setup up down ps logs full-up full-down api worker test test-all lint fmt typecheck eval bench doctor health

env:
	@python -c "import os,shutil; os.path.exists('.env') or (shutil.copy('.env.example','.env'), print('created .env from .env.example - edit the keys'))"

setup: env
	cd $(BACKEND) && $(UV) sync --python 3.11

up: env
	$(COMPOSE) up -d --wait

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail 100

full-up: env
	$(COMPOSE) -f docker-compose.yml -f docker-compose.full.yml up -d --build --wait

full-down:
	$(COMPOSE) -f docker-compose.yml -f docker-compose.full.yml down

api:
	cd $(BACKEND) && $(UV) run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

worker:
	cd $(BACKEND) && $(UV) run python -m app.worker

test:
	cd $(BACKEND) && $(UV) run pytest -m "not integration"

test-all:
	cd $(BACKEND) && $(UV) run pytest

lint:
	cd $(BACKEND) && $(UV) run ruff check app tests eval
	cd $(BACKEND) && $(UV) run mypy app

fmt:
	cd $(BACKEND) && $(UV) run ruff check --fix app tests eval
	cd $(BACKEND) && $(UV) run ruff format app tests eval

eval:
	cd $(BACKEND) && $(UV) run python -m eval.run_eval

bench:
	cd $(BACKEND) && $(UV) run python -m eval.run_bench

doctor:
	cd $(BACKEND) && $(UV) run python -m app.core.doctor

health:
	curl -s http://127.0.0.1:8000/health
