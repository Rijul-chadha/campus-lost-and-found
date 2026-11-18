.PHONY: help up down logs migrate seed test test-unit eval lint fmt typecheck web-dev api-dev worker-dev

help:            ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

up:              ## Start the whole stack (db, redis, s3, mail, api, worker, web)
	@test -f .env || cp .env.example .env
	docker compose up --build -d
	@echo "Web:      http://localhost:3000"
	@echo "API docs: http://localhost:8000/docs"
	@echo "Mailbox:  http://localhost:8025"

down:            ## Stop the stack
	docker compose down

logs:            ## Tail api + worker logs
	docker compose logs -f api worker

migrate:         ## Apply DB migrations
	cd backend && alembic upgrade head

seed:            ## Seed demo campus, locations, desk and users
	cd backend && python -m scripts.seed

test:            ## Run all backend tests
	cd backend && pytest -q

test-unit:       ## Run fast unit tests only (no DB needed)
	cd backend && pytest -q tests/unit tests/eval

eval:            ## Run the matching-quality evaluation and print metrics
	cd backend && python -m tests.eval.run_eval

lint:            ## Lint backend and frontend
	cd backend && ruff check . && ruff format --check .
	cd frontend && npm run lint

fmt:             ## Format backend
	cd backend && ruff format . && ruff check --fix .

typecheck:       ## Static type checks
	cd backend && mypy app
	cd frontend && npm run typecheck

api-dev:         ## Run API locally with reload
	cd backend && uvicorn app.main:app --reload --port 8000

worker-dev:      ## Run worker locally
	cd backend && arq app.workers.main.WorkerSettings --watch app

web-dev:         ## Run frontend locally
	cd frontend && npm run dev
