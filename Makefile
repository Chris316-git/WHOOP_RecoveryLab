.PHONY: setup server init-db sync-whoop connect-google sync-calendar sync test

setup:            ## Install dependencies
	uv sync

server:           ## Start local server for the WHOOP login (open http://localhost:8000/login)
	uv run uvicorn src.api.main:app --port 8000

init-db:          ## Create database tables
	uv run python scripts/init_db.py

sync-whoop:       ## Pull WHOOP data into the database
	uv run python scripts/sync_whoop.py

connect-google:   ## One-time Google Calendar authorization
	uv run python scripts/connect_google.py

sync-calendar:    ## Pull calendar time blocks and compute daily features
	uv run python scripts/sync_calendar.py

sync: sync-whoop sync-calendar

test:
	uv run pytest -q
