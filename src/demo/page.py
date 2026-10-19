"""The public demo page (docs/index.html, served by GitHub Pages). Pure logic.

It shows one day of the real pipeline: the morning brief, the daily agent's loop (what it
observed, the tools it called, the validator's verdict, its notes for tomorrow), the numbered
evidence and its reply, the validator catching tampered replies, one real coach exchange, the
running experiment, and the simulation checks of the statistics.

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
.tag{display:inline-block;background:var(--chip);color:var(--chipink);border-radius:6px;padding:0 6px;font-size:11px}
.loop{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
@media (max-width:820px){.loop{grid-template-columns:1fr}}
.loop ul{margin:6px 0 0;padding-left:18px}.loop code{font-size:12px}
.chat .me{margin-left:auto;max-width:85%;background:var(--ink);color:var(--bg);border-radius:14px;padding:8px 12px;
width:fit-content}.chat .bot{max-width:85%;border:1px solid var(--line);border-radius:14px;padding:10px 12px;
margin:10px 0 6px;white-space:pre-wrap}
.prop{border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-top:10px;max-width:85%}
.fake{display:inline-block;margin-top:8px;background:var(--ink);color:var(--bg);border-radius:8px;padding:6px 12px;
font-size:13px;font-weight:600;opacity:.6}
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


TOPIC_NOTE = {"memory": "personal memory", "agent_notes": "agent's note from yesterday"}


def _short(text: str, n: int = 260) -> str:
    return text if len(text) <= n else text[:n].rstrip() + "…"


def _evidence(case: dict) -> str:
    def topic(t: str) -> str:
        if t.startswith("tool:"):
            return f'<span class="tag">tool result</span> {escape(t[5:])}'
        if t in TOPIC_NOTE:
            return f'<span class="tag">{TOPIC_NOTE[t]}</span>'
        return escape(t)
    rows = "".join(f'<div class="ev" id="ev-{escape(e["id"])}"><span class="id">{escape(e["id"])}</span>'
                   f'<span><span class="topic">{topic(e["topic"])}</span>{escape(_short(e["text"]))}</span></div>'
                   for e in case.get("evidence", []))
    return (f'<div class="card"><h3>What the agent saw</h3><p class="small muted">Numbered evidence: facts computed '
            f'in Python, personal memory, its note from yesterday, and the results of the tools it chose to call.'
            f'</p>{rows}</div>')


def _loop(snapshot: dict) -> str:
    a = snapshot.get("agent") or {}
    case = snapshot.get("case") or {}
    ev = case.get("evidence", [])
    memories = sum(e["topic"] == "memory" for e in ev)
    notes_in = sum(e["topic"] == "agent_notes" for e in ev)
    trace = a.get("trace") or []
    calls = "".join(f'<li><code>{escape(t["tool"])}</code> {escape(json.dumps(t.get("input") or {}))} '
                    f'&rarr; <span class="id cite" data-id="{escape(t["evidence_id"])}">{escape(t["evidence_id"])}'
                    f'</span></li>' for t in trace) or "<li>No extra tools needed today.</li>"
    status = (snapshot.get("reasoning") or {}).get("status", "off")
    revised = " after one revision" if a.get("revised") else ""
    verdict = ("passed every check" + revised if status == "ok"
               else f"{status}: the rule engine's plan was used instead")
    notes = "".join(f"<li>{escape(n)}</li>" for n in a.get("notes") or []) or "<li>None today.</li>"
    return (f'<div class="card loop">'
            f'<div><b>Observe</b><p class="small">Today\'s computed case file, {memories} personal memory '
            f'item{"s" if memories != 1 else ""}, {notes_in} note{"s" if notes_in != 1 else ""} from yesterday.</p>'
            f'<ul class="small">{calls}</ul></div>'
            f'<div><b>Reason</b><p class="small">Claude decides what deserves attention, or that nothing needs to '
            f'change. Code validated the answer: {escape(verdict)}.</p></div>'
            f'<div><b>Act</b><p class="small">One plan in the email. Nothing outside Recovery Lab changes until the '
            f'user taps a button.</p></div>'
            f'<div><b>Learn</b><p class="small">Stored with today\'s plan for tomorrow, next to the user\'s response '
            f'and the outcome measured from the wearable:</p><ul class="small">{notes}</ul></div></div>')


def _coach(snapshot: dict) -> str:
    c = snapshot.get("coach")
    if not c:
        return ""
    used = ", ".join(dict.fromkeys(c.get("tools_used") or [])) or "none"
    props = "".join(
        f'<div class="prop"><b>{escape(p["day"])} · {escape(p["start"])}-{escape(p["end"])}</b>'
        f'<div>{escape(p["title"])}</div><div class="small muted">{escape(p.get("why") or "")}</div>'
        f'<span class="fake">Add to calendar</span></div>' for p in c.get("proposals") or [])
    flag = "" if c.get("checked", True) else ('<div class="small muted">Some numbers could not be verified; the '
                                              'page would show this note.</div>')
    return ('<section><h2>3. The coach: ask it anytime</h2><p class="muted">The email links to a chat with the same '
            'tools plus three more: free time, saving what the user says (goals, preferences, corrections) to '
            'memory, and proposing a calendar block. Proposals are checked in code and written only after a tap. '
            'A real exchange from this snapshot:</p>'
            f'<div class="card chat"><div class="me">{escape(c["question"])}</div>'
            f'<div class="bot">{escape(c["reply"])}</div><div class="small muted">tools it chose: {escape(used)}'
            f'</div>{flag}{props}</div></section>')


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
    agent (notes, trace, revised), coach (question, reply, tools_used, proposals), experiment,
    calibration, power, example_card."""
    pipeline = "".join(
        ('<span class="arrow">&rarr;</span>' if i else "") + f'<div class="step"><b>{a}</b>{escape(b)}</div>'
        for i, (a, b) in enumerate([
            ("Trigger", "WHOOP webhook when the night is scored"),
            ("Analyse", "Python: baselines, trends, load, sleep debt"),
            ("Observe", "evidence, memory, yesterday's notes, tools"),
            ("Reason", "Claude decides; code validates"),
            ("Act", "email; calendar only after a tap"),
            ("Learn", "responses, outcomes, notes, corrections"),
        ]))
    srcdoc = escape(snapshot["email_html"], quote=True)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer"><title>Recovery Lab Demo</title>'
        f'<style>{CSS}</style></head><body><div class="wrap">'
        '<div class="small muted" style="font-weight:700;letter-spacing:.08em">RECOVERY LAB</div>'
        '<h1>A personal health agent that reasons over your own data, remembers what you tell it, and tests '
        'what actually works</h1>'
        '<p class="lead">Every morning, as soon as WHOOP scores the night, an agent reads Python-computed evidence, '
        'its memory of you and its own notes from yesterday, calls tools when it needs more, and decides on one '
        'action, or none. Code checks every claim. A coach chat and randomized N-of-1 experiments close the loop.'
        '</p>'
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
        '<section><h2>2. The daily agent: observe, reason, act, learn</h2><p class="muted">The model never sees raw '
        'records. Every fact it can use is a numbered evidence item, and every number in its answer is checked '
        'against them; if a check fails it gets one revision, then the transparent rule engine\'s plan is used.</p>'
        f'{_loop(snapshot)}'
        f'<div class="grid two" style="margin-top:16px">{_evidence(snapshot["case"])}<div>{_ai_reply(snapshot)}'
        f'{_stress(snapshot.get("stress") or [])}</div></div></section>'
        f'{_coach(snapshot)}'
        '<section><h2>4. Experiments: does a habit actually help me?</h2><p class="muted">The AI may propose an '
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
