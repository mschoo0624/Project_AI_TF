SHELL := /bin/bash

.PHONY: dev reset-test-db test-portal

dev:
	source venv/bin/activate && uv run uvicorn user.app.main:app --reload --port 8001

reset-test-db:
	rm -f /tmp/project_ai_tf_test.db
	sqlite3 /tmp/project_ai_tf_test.db < sql/init_phase1.sql
	sqlite3 /tmp/project_ai_tf_test.db < sql/seed_phase1.sql

test-portal: reset-test-db
	DB_PATH=/tmp/project_ai_tf_test.db venv/bin/uvicorn user.app.main:app --reload --port 8001