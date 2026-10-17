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

RESULT_TITLES = {"started": "Experiment started", "declined_exp": "Not now", "decided": "Saved",
                 "stopped": "Experiment stopped", "recorded": "Answer saved", "added": "Added to your calendar",
                 "moved": "Time changed", "dismissed": "Dismissed",
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


@app.exception_handler(Exception)
async def _unexpected(request: Request, exc: Exception):
    """A readable page instead of a bare "Internal Server Error". The full traceback goes to
    the host's logs (it may contain data, so it is never shown on the page)."""
    import logging

    from src.actions import pages
    logging.getLogger("recovery_lab").exception("unhandled error on %s", request.url.path)
    return HTMLResponse(pages.done("Something went wrong",
                                   f"Nothing was changed. ({type(exc).__name__}; details are in the server log.)"),
                        status_code=500)


@app.get("/a/{token}")
def action_page(token: str, request: Request):
    from src.actions import pages
    from src.actions.service import PlanNotFound
    service, key, t, error = _verify(request, token)
    if error:
        return error
    url = f"/a/{token}"
    if t.action in ("adhere_yes", "adhere_no"):   # experiment answers do not depend on a daily plan
        label = "Yes, I did" if t.action == "adhere_yes" else "No, not last night"
        return _no_store(HTMLResponse(pages.one_tap(url, "Saving your answer…", label)))
    one_tap = {"exp_start": ("Starting the experiment…", "Start the experiment"),
               "exp_decline": ("Saving…", "Not now"), "exp_keep": ("Saving…", "Keep the habit"),
               "exp_extend": ("Extending…", "Extend the experiment"), "exp_drop": ("Saving…", "Drop it")}
    if t.action in one_tap:
        return _no_store(HTMLResponse(pages.one_tap(url, *one_tap[t.action])))
    if t.action == "exp_stop":   # stopping cannot be undone, so it waits for a tap
        return _no_store(HTMLResponse(pages.confirm(url, "Stop the experiment?", "Yes, stop it")))
    if t.action == "exp_browse":
        options, running = service.experiment_options(t)
        return _no_store(HTMLResponse(pages.experiment_list(url, options, running)))
    try:
        plan = service.plan(t)
    except PlanNotFound as exc:
        return HTMLResponse(pages.done("Not found", str(exc)), status_code=404)
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
def action_submit(token: str, request: Request, choice: int | None = None, preset: str | None = None):
    from src.actions import pages
    from src.actions.service import PlanNotFound
    service, key, t, error = _verify(request, token)
    if error:
        return error
    try:
        if t.action in ("adhere_yes", "adhere_no"):
            outcome = service.adhere(t, t.action == "adhere_yes")
        elif t.action == "exp_start":
            outcome = service.start_proposed(t)
        elif t.action == "exp_decline":
            outcome = service.decline(t)
        elif t.action in ("exp_keep", "exp_extend", "exp_drop"):
            outcome = service.decide(t, t.action.removeprefix("exp_"))
        elif t.action == "exp_stop":
            outcome = service.stop_experiment(t)
        elif t.action == "exp_browse":
            outcome = service.start_preset(t, preset or "")
        elif t.action == "add":
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
    title = RESULT_TITLES.get(outcome.status, "Done")
    if outcome.calendar in ("failed", "not_connected"):
        title = "Saved, but not on your calendar yet"
    return _no_store(HTMLResponse(pages.done(
        title, outcome.message, outcome.block,
        undo_url=_link(t, "undo", key) if outcome.can_undo else None,
        not_useful_url=_link(t, "not_useful", key) if outcome.ask_not_useful else None)))


@app.get("/healthz")
def healthz(deep: bool = False):
    """Liveness. With ?deep=1, also check the settings and the database connection. Only
    yes/no answers and an error type are returned, never values."""
    if not deep:
        return {"ok": True}
    from sqlalchemy import text

    from src.settings import Settings
    s = Settings.from_env()
    out = {"ok": True, "database_url_set": bool(s.database_url), "signing_key_set": bool(s.action_signing_key),
           "encryption_key_set": bool(s.token_encryption_key)}
    try:
        from src.db.session import default_session_factory
        with default_session_factory()() as session:
            session.execute(text("select 1"))
            cols = {r[0] for r in session.execute(text(
                "select column_name from information_schema.columns where table_name = 'daily_plans'"))}
        out["database"] = "ok"
        out["schema_up_to_date"] = {"response", "calendar_status", "outcome"} <= cols
    except Exception as exc:
        out.update(ok=False, database=type(exc).__name__)
    return out
