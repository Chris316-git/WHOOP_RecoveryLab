"""The public demo page (docs/index.html, served by GitHub Pages). Pure logic.

It shows one day of the real pipeline: the morning brief, the numbered evidence the AI
reasoned over, its reply and the validator's verdict, the validator catching tampered
replies, the running experiment, and the simulation checks of the statistics.

What it never contains: action links (buttons are inert), calendar event titles (only
busy/free time ever leaves the calendar module), email addresses or user ids. The script
that writes the page (scripts/demo.py) scans the HTML for those before saving it.
"""
import copy
import json
import re
from html import escape

from src.planner.focus import TITLES
from src.reasoning.validate import validate

REPO_URL = "https://github.com/Chris316-git/WHOOP_RecoveryLab"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
ARM_LABEL = {"treatment": "habit night", "control": "comparison night"}


# ---------- validator stress test ----------

def tampered_replies(output: dict, case: dict) -> list[tuple[str, dict]]:
    """Copies of today's real AI reply, each broken in one way the validator must catch."""
    if not output or not output.get("reasons"):
        return []
    out = []

    def variant(label: str, change) -> None:
        o = copy.deepcopy(output)
        change(o)
        out.append((label, o))

    variant("Adds a number that is in no evidence item",
            lambda o: o["reasons"][0].update(text=o["reasons"][0]["text"].rstrip(".") + ", up 913 points."))
    variant("Cites an evidence item that does not exist",
            lambda o: o["reasons"][0].update(evidence=["E99"]))
    variant("Describes a body state the data cannot show",
            lambda o: o.update(headline="You are under-recovered and fatigued today."))
    variant("Suggests an all-out session at 03:00",
            lambda o: o.update(focus_type="go_hard", title="Max effort intervals",
                               action=dict(type="calendar_block", title="Hard session: sprint intervals",
                                           start="03:00", minutes=60)))
    variant("Gives five reasons instead of at most three",
            lambda o: o.update(reasons=(o["reasons"] * 5)[:5]))
    return out


def stress_test(output: dict, case: dict, rule_summary: dict) -> list[dict]:
    rows = []
    for label, o in tampered_replies(output, case):
        _, problems = validate(o, case, rule_summary)
        rows.append(dict(label=label, problems=problems, caught=bool(problems)))
    return rows


# ---------- page ----------

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#111827;--ink2:#374151;--muted:#6b7280;--line:#e5e7eb;--accent:#2563eb;
--good:#0f9d58;--bad:#d03b3b;--chip:#eef2ff;--chipink:#3730a3;--code:#f3f4f6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1115;--card:#171a21;--ink:#e5e7eb;
--ink2:#c9cdd4;--muted:#9aa1ac;--line:#2a2f3a;--accent:#7aa2ff;--good:#4cc38a;--bad:#f07171;--chip:#22263a;
--chipink:#b9c3ff;--code:#1f232c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:34px;line-height:1.15;margin:0 0 8px}h2{font-size:22px;margin:0 0 6px}
h3{font-size:15px;margin:0 0 10px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
p{margin:0 0 12px}.muted{color:var(--muted)}.small{font-size:13px}a{color:var(--accent)}
.lead{font-size:18px;color:var(--ink2);max-width:760px}
.links a{display:inline-block;margin:10px 10px 0 0;padding:8px 14px;border:1px solid var(--line);border-radius:10px;
text-decoration:none;font-weight:600;background:var(--card)}
.stamp{display:inline-block;margin-top:14px;font-size:13px;color:var(--muted);border:1px dashed var(--line);
border-radius:10px;padding:6px 10px}
section{margin-top:40px}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px}
.grid{display:grid;gap:16px}.two{grid-template-columns:1fr 1fr}@media (max-width:820px){.two{grid-template-columns:1fr}}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:14px}
.step{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px;font-size:14px}
.step b{display:block;font-size:13px}.arrow{color:var(--muted)}
.ev{display:flex;gap:10px;padding:7px 0;border-top:1px solid var(--line);font-size:14px}
.ev:first-of-type{border-top:0}.id{flex:0 0 auto;font:600 12px ui-monospace,Menlo,monospace;background:var(--chip);
color:var(--chipink);border-radius:6px;padding:2px 6px;height:fit-content}
.topic{color:var(--muted);font-size:12px;display:block}
.ev.hl{background:var(--chip);border-radius:8px}
.reason{padding:10px 0;border-top:1px solid var(--line);font-size:15px}.reason:first-of-type{border-top:0}
.cite{cursor:pointer;margin-left:4px}
.pill{display:inline-block;border-radius:999px;padding:2px 10px;font-size:13px;font-weight:600}
.ok{background:rgba(15,157,88,.12);color:var(--good)}.no{background:rgba(208,59,59,.12);color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 6px;
border-top:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600;border-top:0}
.scroll{overflow-x:auto}
iframe{width:100%;border:0;border-radius:14px;background:#f3f4f6;min-height:900px}
pre{background:var(--code);border-radius:10px;padding:12px;overflow-x:auto;font-size:12px;max-height:360px}
details summary{cursor:pointer;color:var(--accent);font-size:14px;margin-top:10px}
.light{background:#f3f4f6;border-radius:14px;padding:14px;color:#111827}
footer{margin-top:48px;font-size:13px;color:var(--muted)}
"""

JS = """
document.querySelectorAll('.cite').forEach(function(c){
  function ev(){return document.getElementById('ev-'+c.dataset.id);}
  c.addEventListener('mouseenter',function(){var e=ev();if(e)e.classList.add('hl');});
  c.addEventListener('mouseleave',function(){var e=ev();if(e)e.classList.remove('hl');});
  c.addEventListener('click',function(){var e=ev();if(e)e.scrollIntoView({behavior:'smooth',block:'center'});});
});
var f=document.getElementById('brief');
if(f){f.addEventListener('load',function(){try{f.style.height=(f.contentDocument.body.scrollHeight+24)+'px';}catch(e){}});}
"""


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def _pct1(x: float) -> str:
    return f"{100 * x:.1f}%"


def _value(v) -> str:
    return "-" if v is None else f"{v:g}"


def _cites(ids: list[str]) -> str:
    return "".join(f'<span class="id cite" data-id="{escape(i)}">{escape(i)}</span>' for i in ids or [])


def _evidence(case: dict) -> str:
    rows = "".join(f'<div class="ev" id="ev-{escape(e["id"])}"><span class="id">{escape(e["id"])}</span>'
                   f'<span><span class="topic">{escape(e["topic"])}</span>{escape(e["text"])}</span></div>'
                   for e in case.get("evidence", []))
    return f'<div class="card"><h3>Evidence file (computed in Python)</h3>{rows}</div>'


def _ai_reply(snapshot: dict) -> str:
    r = snapshot.get("reasoning") or {}
    out, status = r.get("output"), r.get("status", "off")
    rule = snapshot.get("rule_focus") or {}
    rule_title = rule.get("title") or TITLES.get(rule.get("focus"), rule.get("focus") or "-")
    pill = ('<span class="pill ok">Validator: passed</span>' if status == "ok"
            else f'<span class="pill no">Validator: {escape(status)}</span>')
    problems = (f'<p class="small muted">Problems found: {escape(", ".join(r.get("problems") or []))}. '
                'The email fell back to the rule engine.</p>' if status != "ok" and r.get("problems") else "")
    if not out:
        return (f'<div class="card"><h3>AI reply</h3>{pill}<p class="muted" style="margin-top:10px">No AI reply '
                f'today, so the rule engine planned the day: <b>{escape(rule_title)}</b>.</p></div>')
    reasons = "".join(f'<div class="reason">{escape(str(x.get("text")))}{_cites(x.get("evidence"))}</div>'
                      for x in out.get("reasons") or [])
    counter = "".join(f'<div class="reason muted">{escape(str(x.get("text")))}{_cites(x.get("evidence"))}</div>'
                      for x in out.get("counter") or [])
    a = out.get("action") or {}
    action = escape(str(a.get("title") or ""))
    if a.get("type") == "calendar_block":
        action = f'{escape(str(a.get("start")))} for {escape(str(a.get("minutes")))} min · {action}'
    same = rule.get("focus") == out.get("focus_type")
    compare = (f'<p class="small muted">The rule engine, run on the same data, picked '
               f'<b>{escape(rule_title)}</b>{" as well" if same else ""}. Both are stored, so the two engines can '
               'be compared over time.</p>')
    raw = escape(json.dumps(out, indent=2, ensure_ascii=False))
    return (f'<div class="card"><h3>AI reply ({escape(snapshot.get("model") or "Claude")})</h3>{pill}'
            f'<h2 style="margin-top:12px">{escape(str(out.get("title")))}</h2>'
            f'<p class="muted">{escape(str(out.get("headline") or ""))}</p>'
            f'<p class="small"><b>Action:</b> {action}</p>'
            f'<div class="small muted" style="margin-top:8px">Reasons, with the evidence they cite (hover to '
            f'highlight):</div>{reasons}'
            + (f'<div class="small muted" style="margin-top:8px">Pointing the other way:</div>{counter}'
               if counter else "")
            + problems + compare
            + f'<details><summary>Raw JSON reply</summary><pre>{raw}</pre></details></div>')


def _stress(rows: list[dict]) -> str:
    if not rows:
        return ""
    body = "".join(
        f'<tr><td>{escape(r["label"])}</td><td>'
        + (f'<span class="pill ok">caught</span> <span class="small muted">{escape(", ".join(r["problems"]))}</span>'
           if r["caught"] else '<span class="pill no">missed</span>')
        + '</td></tr>' for r in rows)
    caught = sum(r["caught"] for r in rows)
    return (f'<div class="card" style="margin-top:16px"><h3>Validator stress test</h3>'
            f'<p class="small muted">Today\'s real AI reply, broken on purpose in {len(rows)} ways and sent back '
            f'through the same validator. Caught: {caught} of {len(rows)}. Any failed check means the AI plan is '
            f'discarded and the rule engine\'s plan is used.</p>'
            f'<div class="scroll"><table><tr><th>Tampered reply</th><th>Validator</th></tr>{body}</table></div></div>')


def _experiment(snapshot: dict) -> str:
    x = snapshot.get("experiment")
    if not x:
        return ('<div class="card"><h3>Running experiment</h3><p class="muted">No experiment is running right '
                'now.</p></div>')
    rows = "".join(
        f'<tr><td>{escape(n["day"])}</td><td>{escape(ARM_LABEL.get(n["arm"], n["arm"]))}</td>'
        f'<td>{escape({"yes": "yes", "no": "no"}.get(n.get("adherence"), "-") if n["arm"] == "treatment" else "")}'
        f'</td><td>{_value(n.get("outcome"))}</td></tr>'
        for n in x["nights"])
    return (f'<div class="card"><h3>Running experiment · night {x["night"]} of {x["total"]}</h3>'
            f'<h2>{escape(x["title"])}</h2><p class="muted">{escape(x["question"])}</p>'
            f'<p class="small">Nights come in pairs; a seeded coin flip decides which night of each pair is the '
            f'habit night. Adherence comes from a one-tap Yes/No the next morning, never from the outcome. '
            f'Future assignments stay hidden, and there are no interim results: peeking and stopping early would '
            f'inflate false positives.</p>'
            f'<div class="scroll"><table><tr><th>Night</th><th>Assigned</th><th>Kept the habit</th>'
            f'<th>{escape(x["outcome_label"])}</th></tr>{rows}</table></div></div>')


def _stats(snapshot: dict) -> str:
    c, pw, ex = snapshot["calibration"], snapshot["power"], snapshot.get("example_card")
    effects = [k for k in pw[0] if k != "nights"]
    head = "".join(f"<th>+{e:g} pts</th>" for e in effects)
    body = "".join(f'<tr><td>{r["nights"]} nights</td>' + "".join(f"<td>{_pct(r[e])}</td>" for e in effects)
                   + "</tr>" for r in pw)
    example = (f'<div class="light" style="margin-top:12px"><table role="presentation" width="100%">{ex}</table></div>'
               if ex else "")
    return (f'<div class="grid two" style="margin-top:16px"><div class="card"><h3>Is the statistics honest?</h3>'
            f'<p class="small">{c["sims"]:,} simulated experiments with <b>no true effect</b>, on autocorrelated '
            f'AR(1) nights, analysed by the same code:</p>'
            f'<table><tr><td>False "clear result" rate (target 5%)</td><td><b>{_pct1(c["false_positive_rate"])}</b>'
            f'</td></tr><tr><td>95% interval contains the true effect</td><td><b>{_pct1(c["coverage"])}</b></td></tr>'
            f'</table><p class="small" style="margin-top:14px">Chance of a "helped" verdict when the habit really '
            f'raises sleep performance by:</p><div class="scroll"><table><tr><th>Length</th>{head}</tr>{body}'
            f'</table></div><p class="small muted" style="margin-top:8px">One person, two weeks: only large effects '
            f'are reliably found, and the result card says "inconclusive" rather than guessing.</p></div>'
            f'<div class="card"><h3>What a finished result looks like</h3><p class="small muted">Simulated '
            f'experiment (synthetic data, true effect +5 points), analysed and worded by the real code.</p>'
            f'{example}</div></div>')


def build_page(snapshot: dict) -> str:
    """snapshot: date, time, timezone, email_html, case, reasoning, rule_focus, model, stress,
    experiment, calibration, power, example_card."""
    pipeline = "".join(
        ('<span class="arrow">&rarr;</span>' if i else "") + f'<div class="step"><b>{a}</b>{escape(b)}</div>'
        for i, (a, b) in enumerate([
            ("Ingest", "WHOOP + Google Calendar, OAuth, incremental sync"),
            ("Analyse", "personal baselines, trends, load, sleep debt"),
            ("Evidence", "numbered facts, no raw records"),
            ("Reason", "Claude plans the day"),
            ("Validate", "citations, numbers, safety, calendar fit"),
            ("Act", "email, one-tap calendar, experiments"),
        ]))
    srcdoc = escape(snapshot["email_html"], quote=True)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer"><title>Recovery Lab Demo</title>'
        f'<style>{CSS}</style></head><body><div class="wrap">'
        '<div class="small muted" style="font-weight:700;letter-spacing:.08em">RECOVERY LAB</div>'
        '<h1>A morning brief that reasons over your own data, and experiments that test what actually works</h1>'
        '<p class="lead">Recovery Lab reads WHOOP and Google Calendar data, lets an LLM plan the day from numbered, '
        'precomputed evidence, checks every claim in code, and runs randomized N-of-1 experiments with honest '
        'statistics.</p>'
        f'<div class="links"><a href="{REPO_URL}">Source on GitHub</a>'
        f'<a href="{REPO_URL}/blob/main/PRIVACY.md">Privacy design</a></div>'
        f'<div class="stamp">Real data from the author\'s own WHOOP · snapshot of {escape(snapshot["weekday"])} '
        f'{escape(snapshot["date"])}, {escape(snapshot["time"])} ({escape(snapshot["timezone"])}) · calendar shown '
        f'only as busy/free · buttons disabled</div>'
        f'<div class="flow">{pipeline}</div>'
        '<section><h2>1. The morning brief</h2><p class="muted">The email exactly as it was rendered for this '
        'snapshot. Read it in 15 seconds; acting on it is optional. The buttons normally add the plan to the '
        'calendar with one tap, with Undo.</p>'
        f'<iframe id="brief" title="Morning brief" sandbox="allow-same-origin" srcdoc="{srcdoc}"></iframe></section>'
        '<section><h2>2. How the AI decided</h2><p class="muted">The model never sees raw records. It gets a case '
        'file of numbered facts, all computed in Python, and must cite them. Code then checks the reply; if any '
        'check fails, the transparent rule engine\'s plan is used instead.</p>'
        f'<div class="grid two">{_evidence(snapshot["case"])}<div>{_ai_reply(snapshot)}'
        f'{_stress(snapshot.get("stress") or [])}</div></div></section>'
        '<section><h2>3. Experiments: does a habit actually help me?</h2><p class="muted">The AI may propose an '
        'experiment from a fixed list when the data makes it relevant; randomization, adherence and statistics stay '
        'in code. The verdict is pre-specified: helped, worse, no meaningful effect, or inconclusive.</p>'
        f'{_experiment(snapshot)}{_stats(snapshot)}</section>'
        '<footer>Not medical advice. One person\'s data says nothing about other people. This page is generated by '
        f'<code>scripts/demo.py</code> from one run of the real pipeline; nothing on it is edited by hand. '
        f'<a href="{REPO_URL}">github.com/Chris316-git/WHOOP_RecoveryLab</a></footer>'
        f'</div><script>{JS}</script></body></html>')


def privacy_problems(html: str, forbidden: list[str]) -> list[str]:
    """Things that must never be on the public page."""
    problems = []
    if _EMAIL.search(html):
        problems.append("an email address")
    if "/a/" in html or "/coach/" in html:
        problems.append("an action link")
    problems += [f"a private value ({f[:3]}...)" for f in forbidden if f and f in html]
    return problems
