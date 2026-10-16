.PHONY: setup server init-db sync-whoop connect-google sync-calendar sync gen-key migrate-tokens daily daily-now report-preview settings test

setup:            ## Install dependencies
	uv sync

server:           ## Start local server for the WHOOP login (open http://localhost:8000/login)
	uv run uvicorn src.api.main:app --port 8000

init-db:          ## Create database tables (safe to re-run; adds new tables)
	uv run python scripts/init_db.py

sync-whoop:       ## Pull WHOOP data into the database
	uv run python scripts/sync_whoop.py

connect-google:   ## One-time Google Calendar authorization
	uv run python scripts/connect_google.py

sync-calendar:    ## Pull calendar time blocks and compute daily features
	uv run python scripts/sync_calendar.py

sync: sync-whoop sync-calendar

gen-key:          ## Print a new TOKEN_ENCRYPTION_KEY
	@uv run python -c "from src.security import new_key; print(new_key())"

migrate-tokens:   ## Copy .tokens/ credentials into the encrypted database table
	uv run python scripts/migrate_tokens.py

daily:            ## Email today's report if it is due (same check as the scheduled job)
	uv run python scripts/daily.py

daily-now:        ## Sync everything and email today's report right now
	uv run python scripts/daily.py --now

report-preview:   ## Sync everything and save today's report to data/reports/ (no email)
	uv run python scripts/daily.py --preview

settings:         ## Show or change report settings, e.g. make settings ARGS="--time 10:30"
	uv run python scripts/settings.py $(ARGS)

test:
	uv run pytest -q
