"""Web server: the WHOOP login flow and the action links from the email
(Add to calendar, Change time, Dismiss).

Local:  make server   then open http://localhost:8000/login
Hosted: see render.yaml (the action links need a public URL: PUBLIC_BASE_URL).

Mail scanners often open links in emails automatically, so a GET never changes anything:
it returns a page that submits a POST by itself (one tap for the user, nothing for a
scanner that does not run scripts). Results offer Undo.
"""
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src import config
from src.ingestion import whoop_auth
from src.ingestion.token_store import get_whoop_store

app = FastAPI(title="Recovery Lab")
store = get_whoop_store()
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


# ---------------- Add to calendar / Change time / Dismiss ----------------

RESULT_TITLES = {"added": "Added to your calendar", "moved": "Time changed", "dismissed": "Dismissed",
                 "not_useful": "Thanks for the feedback", "undone": "Undone", "already": "Already done",
                 "nothing": "Nothing to do"}


def _actions(request: Request):
    """The ActionService and signing key, created on first use (tests can set app.state.*)."""
    state = request.app.state
    if not hasattr(state, "action_service"):
        from src.actions.service import ActionService
        from src.db.session import default_session_factory
        from src.settings import Settings
        settings = Settings.from_env()
        state.action_service = ActionService(default_session_factory(), default_tz=settings.report_timezone)
        state.signing_key = settings.action_signing_key
    return state.action_service, state.signing_key


def _verify(request: Request, token: str):
    from src.actions import pages
    from src.actions.tokens import InvalidToken, verify
    service, key = _actions(request)
    try:
        return service, key, verify(token, key), None
    except InvalidToken as exc:
        error = HTMLResponse(pages.done("Link not valid", str(exc).capitalize() + "."), status_code=400)
        return service, key, None, error


def _link(t, action: str, key: str) -> str:
    """A follow-up link (Undo, Not useful) for the same plan, expiring with the original one."""
    from dataclasses import replace

    from src.actions.tokens import sign
    return f"/a/{sign(replace(t, action=action), key)}"


def _no_store(response: HTMLResponse) -> HTMLResponse:
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/a/{token}")
def action_page(token: str, request: Request):
    from src.actions import pages
    from src.actions.service import PlanNotFound
    service, key, t, error = _verify(request, token)
    if error:
        return error
    try:
        plan = service.plan(t)
    except PlanNotFound as exc:
        return HTMLResponse(pages.done("Not found", str(exc)), status_code=404)
    url = f"/a/{token}"
    if t.action == "add":
        if not plan["block"]:
            return _no_store(HTMLResponse(pages.done("Nothing to schedule", "Today's suggestion has no time block.")))
        if plan["calendar_status"] == "scheduled":
            return _no_store(HTMLResponse(pages.done(RESULT_TITLES["already"], "This is already on your calendar.",
                                                     plan["final_block"], undo_url=_link(t, "undo", key))))
        return _no_store(HTMLResponse(pages.one_tap(url, "Adding to your calendar…", "Add to calendar",
                                                    plan["block"])))
    if t.action == "change":
        return _no_store(HTMLResponse(pages.change_options(url, plan, service.options(t))))
    if t.action == "dismiss":
        return _no_store(HTMLResponse(pages.one_tap(url, "Dismissing…", "Dismiss today's suggestion")))
    if t.action == "not_useful":
        return _no_store(HTMLResponse(pages.one_tap(url, "Saving…", "Mark today's suggestion as not useful")))
    return _no_store(HTMLResponse(pages.confirm(url, "Undo?", "Undo")))


@app.post("/a/{token}")
def action_submit(token: str, request: Request, choice: int | None = None):
    from src.actions import pages
    from src.actions.service import PlanNotFound
    service, key, t, error = _verify(request, token)
    if error:
        return error
    try:
        if t.action == "add":
            outcome = service.add(t)
        elif t.action == "change":
            outcome = service.change(t, -1 if choice is None else choice)
        elif t.action == "dismiss":
            outcome = service.dismiss(t)
        elif t.action == "not_useful":
            outcome = service.dismiss(t, not_useful=True)
        else:
            outcome = service.undo(t)
    except PlanNotFound as exc:
        return HTMLResponse(pages.done("Not found", str(exc)), status_code=404)
    return _no_store(HTMLResponse(pages.done(
        RESULT_TITLES.get(outcome.status, "Done"), outcome.message, outcome.block,
        undo_url=_link(t, "undo", key) if outcome.can_undo else None,
        not_useful_url=_link(t, "not_useful", key) if outcome.ask_not_useful else None)))


@app.get("/healthz")
def healthz():
    return {"ok": True}
