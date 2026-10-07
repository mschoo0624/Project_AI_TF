SHELL := /bin/bash

.PHONY: dev frontend reset-test-db init-test-db randomize-assignment-data test-portal assignment-portal kill-portal stt-dev stt-kill-portal

dev:
	source venv/bin/activate && uv run uvicorn user.app.main:app --reload --port 8002

stt-dev:
	source venv/bin/activate && uv run uvicorn stt.app.main:app --reload --port 8003

frontend:
	cd ../frontend && npm run dev -- --host 0.0.0.0

reset-test-db:
	rm -f /tmp/project_ai_tf_test.db
	sqlite3 /tmp/project_ai_tf_test.db < sql/init_phase1.sql
	sqlite3 /tmp/project_ai_tf_test.db < sql/seed_phase1.sql

init-test-db:
	@if [ ! -f /tmp/project_ai_tf_test.db ]; then \
		sqlite3 /tmp/project_ai_tf_test.db < sql/init_phase1.sql && \
		sqlite3 /tmp/project_ai_tf_test.db < sql/seed_phase1.sql; \
	fi

randomize-assignment-data: reset-test-db
	sqlite3 /tmp/project_ai_tf_test.db < sql/randomize_assignment_test.sql

test-portal: init-test-db
	DB_PATH=/tmp/project_ai_tf_test.db venv/bin/uvicorn user.app.main:app --reload --port 8002

assignment-portal: randomize-assignment-data
	DB_PATH=/tmp/project_ai_tf_test.db venv/bin/uvicorn user.app.main:app --reload --port 8002

kill-portal:
	fuser -k 8002/tcp || true

stt-kill-portal:
	fuser -k 8003/tcp || true