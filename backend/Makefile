SHELL := /bin/bash

.PHONY: dev frontend reset-test-db randomize-assignment-data test-portal assignment-portal kill-portal

dev:
	source venv/bin/activate && uv run uvicorn user.app.main:app --reload --port 8002

frontend:
	cd ../frontend && npm run dev -- --host 0.0.0.0

reset-test-db:
	rm -f /tmp/project_ai_tf_test.db
	sqlite3 /tmp/project_ai_tf_test.db < sql/init_phase1.sql
	sqlite3 /tmp/project_ai_tf_test.db < sql/seed_phase1.sql

randomize-assignment-data: reset-test-db
	sqlite3 /tmp/project_ai_tf_test.db < sql/randomize_assignment_test.sql

test-portal: reset-test-db
	DB_PATH=/tmp/project_ai_tf_test.db venv/bin/uvicorn user.app.main:app --reload --port 8002

assignment-portal: randomize-assignment-data
	DB_PATH=/tmp/project_ai_tf_test.db venv/bin/uvicorn user.app.main:app --reload --port 8002

kill-portal:
	fuser -k 8002/tcp || true