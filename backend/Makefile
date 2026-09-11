SHELL := /bin/bash

.PHONY: dev

dev:
	source venv/bin/activate && uv run uvicorn user.app.main:app --reload --port 8001