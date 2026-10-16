"""Local web server for the WHOOP login flow.

Run:  make server   then open http://localhost:8000/login
"""
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from src import config
from src.ingestion import whoop_auth
from src.ingestion.token_store import FileTokenStore

app = FastAPI(title="Recovery Lab")
store = FileTokenStore(config.WHOOP_TOKEN_DIR)
_pending_states: set[str] = set()  # fine for a single local process


@app.get("/")
def index():
    return HTMLResponse('<h2>Recovery Lab</h2><p><a href="/login">Connect WHOOP</a></p>')


@app.get("/login")
def login():
    state = whoop_auth.new_state()
    _pending_states.add(state)
    return RedirectResponse(whoop_auth.build_authorization_url(state))


@app.get("/callback")
def callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        raise HTTPException(400, f"WHOOP authorization failed: {error}")
    if not code or state not in _pending_states:
        raise HTTPException(400, "Invalid or expired login attempt. Start again at /login.")
    _pending_states.discard(state)

    token = whoop_auth.exchange_code(code)
    resp = httpx.get(
        f"{config.WHOOP_API_BASE}/user/profile/basic",
        headers={"Authorization": f"Bearer {token.access_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    profile = resp.json()
    user_id = str(profile["user_id"])
    store.save(user_id, token)  # keyed by WHOOP user id, so users never overwrite each other

    return HTMLResponse(
        f"<h2>Connected, {profile.get('first_name', '')}!</h2>"
        "<p>You can close this tab and run <code>make sync-whoop</code>.</p>"
    )
