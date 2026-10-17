"""Small HTML pages for the action links (mobile-friendly).

Mail scanners open links in emails on their own, so a plain GET never changes anything.
For one-tap actions the GET page submits itself with a line of JavaScript (most scanners do
not run scripts) and shows a normal button when scripts are off. Every result offers Undo.
"""
from html import escape

INK, MUTED, LINE = "#111827", "#6b7280", "#e5e7eb"


def page(title: str, body: str) -> str:
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer"><meta name="robots" content="noindex">'
        f'<title>{escape(title)} · Recovery Lab</title></head>'
        f'<body style="margin:0;background:#f3f4f6;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        f'color:{INK}"><div style="max-width:480px;margin:0 auto;padding:28px 16px">'
        f'<div style="font-size:13px;font-weight:700;letter-spacing:.08em">RECOVERY LAB</div>'
        f'<div style="background:#fff;border:1px solid {LINE};border-radius:14px;padding:22px;margin-top:14px">'
        f'<h1 style="font-size:22px;margin:0 0 10px">{escape(title)}</h1>{body}</div></div></body></html>'
    )


def button(action_url: str, label: str, primary: bool = True, form_id: str | None = None) -> str:
    style = (f"background:{INK};color:#fff;border:0" if primary
             else f"background:#fff;color:{INK};border:1px solid {LINE}")
    fid = f' id="{form_id}"' if form_id else ""
    return (f'<form{fid} method="post" action="{escape(action_url)}" style="margin:10px 0 0">'
            f'<button type="submit" style="{style};width:100%;padding:12px 14px;border-radius:10px;'
            f'font-size:15px;font-weight:600;text-align:left">{escape(label)}</button></form>')


def text_button(action_url: str, label: str) -> str:
    return (f'<form method="post" action="{escape(action_url)}" style="margin:14px 0 0">'
            f'<button type="submit" style="background:none;border:0;padding:0;color:{MUTED};font-size:13px;'
            f'text-decoration:underline;cursor:pointer">{escape(label)}</button></form>')


def block_text(b: dict) -> str:
    return f"{b['start']}-{b['end']} · {b['title']}"


def one_tap(url: str, title: str, label: str, block: dict | None = None) -> str:
    """Submits itself right away; the button is the fallback when scripts are off."""
    extra = f'<p style="font-size:17px;font-weight:600;margin:0">{escape(block_text(block))}</p>' if block else ""
    return page(title, extra + button(url, label, form_id="go")
                + '<script>document.getElementById("go").submit();</script>')


def confirm(url: str, title: str, label: str) -> str:
    return page(title, button(url, label))


def change_options(url: str, plan: dict, options: list[dict]) -> str:
    if not options:
        return page("No other free time today",
                    f'<p style="color:{MUTED}">Your calendar has no other free slot that fits today.</p>')
    current = plan["final_block"] if plan.get("calendar_status") == "scheduled" else plan["block"]
    buttons = "".join(button(f"{url}?choice={i}", f"{o['start']}-{o['end']} · {o['label']}", primary=False)
                      for i, o in enumerate(options))
    return page("Pick another time", f'<p style="color:{MUTED};margin:0">{escape(plan["title"])}. '
                f'Currently {escape(block_text(current))}.</p>{buttons}')


def done(title: str, message: str, block: dict | None = None, undo_url: str | None = None,
         not_useful_url: str | None = None) -> str:
    extra = f'<p style="font-size:17px;font-weight:600;margin:0 0 8px">{escape(block_text(block))}</p>' if block else ""
    body = extra + f'<p style="color:{MUTED};margin:0">{escape(message)}</p>'
    if undo_url:
        body += button(undo_url, "Undo", primary=False)
    if not_useful_url:
        body += text_button(not_useful_url, "The suggestion itself wasn't useful")
    return page(title, body)


def experiment_list(url: str, options: list[dict], running: bool) -> str:
    if running:
        return page("Experiments", f'<p style="color:{MUTED}">An experiment is already running. You can start '
                    'another one when it ends.</p>')
    items = "".join(
        f'<div style="border-top:1px solid {LINE};padding:14px 0 4px">'
        f'<div style="font-size:16px;font-weight:600">{escape(o["title"])}</div>'
        f'<div style="color:{MUTED};font-size:14px;margin-top:4px">{escape(o["question"])} '
        f'{o["nights"]} nights; on half of them, chosen at random: {escape(o["treatment"])}</div>'
        + button(f"{url}?preset={o['key']}", "Start this experiment", primary=False) + "</div>"
        for o in options)
    return page("Start an experiment", f'<p style="color:{MUTED};margin:0 0 6px">Each experiment randomly '
                'assigns nights, asks one Yes/No question the next morning, and reports what changed for you.</p>'
                + items)
