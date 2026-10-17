"""Turn a daily summary into an email (subject, HTML, plain text). Formatting only."""
from html import escape

STATUS_TEXT = {"better": "better than usual", "worse": "worse than usual", "typical": "typical",
               "no_baseline": "building baseline", "no_data": "no data"}


def _fmt(value, unit: str) -> str:
    if value is None:
        return "-"
    if unit == "min":
        h, m = divmod(int(round(value)), 60)
        return f"{h}h {m:02d}m" if h else f"{m}m"
    return f"{value:g} {unit}" if unit != "%" else f"{value:g}%"


def _delta(m: dict) -> str:
    if m["delta"] is None:
        return ""
    if m["delta"] == 0:
        return "same as usual"
    sign = "+" if m["delta"] > 0 else "-"
    size = f"{abs(m['delta']):g} pts" if m["unit"] == "%" else _fmt(abs(m["delta"]), m["unit"])
    return f"{sign}{size} vs usual"


def _events(n: int) -> str:
    return f"{n} event" + ("" if n == 1 else "s")


def _hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def trend_lines(summary: dict) -> list[tuple[str, str]]:
    """(text, tone) lines for the Trends section; only signals with enough data appear."""
    sig = summary.get("signals") or {}
    lines: list[tuple[str, str]] = []
    hrv = sig.get("hrv")
    if hrv:
        tone = {"below": "bad", "above": "good"}.get(hrv["status"], "neutral")
        lines.append((f"HRV, last 7 days: {hrv['recent_mean']:g} ms, {hrv['status']} your normal range "
                      f"({hrv['normal_low']:g}-{hrv['normal_high']:g})", tone))
    rhr = sig.get("resting_hr")
    if rhr:
        tone = {"above": "bad", "below": "good"}.get(rhr["status"], "neutral")
        lines.append((f"Resting heart rate, last 7 days: {rhr['recent_mean']:g} bpm, {rhr['status']} your normal "
                      f"range ({rhr['normal_low']:g}-{rhr['normal_high']:g})", tone))
    sl = sig.get("sleep")
    if sl:
        need = f"{_hm(sl['need_min'])} need" + (" (assumed)" if sl["need_source"] != "whoop" else "")
        if sl["shortfall_min"] >= 60:
            lines.append((f"Sleep, last {sl['nights_measured']} nights: {_hm(sl['shortfall_min'])} short of your "
                          f"{need}; {sl['nights_short']} short nights", "bad"))
        else:
            lines.append((f"Sleep, last {sl['nights_measured']} nights: on track with your {need}", "good"))
    load = sig.get("load")
    if load:
        label = {"low": "lighter than usual", "normal": "normal", "high": "high",
                 "very_high": "very high"}[load["level"]]
        text = f"Training load: {load['ratio']:g}x your 4-week average ({label})"
        if load["consecutive_hard_days"] >= 2:
            text += f"; {load['consecutive_hard_days']} hard days in a row"
        lines.append((text, "bad" if load["level"] in ("high", "very_high") else "neutral"))
    wd = sig.get("weekday")
    if wd:
        lines.append((f"Tonight: {wd['weekday']} is usually a short night for you "
                      f"({abs(wd['gap_min'])} min less, {wd['nights']} recent {wd['weekday']}s)", "neutral"))
    if not lines:  # not enough history for trends yet: fall back to the simple 7-day means
        for key, t in summary.get("week_trend", {}).items():
            label = "Recovery" if key == "recovery_score" else "HRV"
            lines.append((f"{label}, last 7 days: {t['week_mean']:g} (usual {t['baseline_median']:g})", "neutral"))
    return lines


def subject(summary: dict) -> str:
    rec = summary["metrics"][0]["value"]
    head = f"Recovery Lab · {summary['weekday']} {summary['date']}"
    if rec is None:
        return f"{head} · last night not scored yet"
    focus = summary.get("focus") or {}
    tail = f" · {focus['title']}" if focus.get("focus") not in (None, "none") else ""
    return f"{head} · Recovery {rec:g}% ({summary['recovery_zone']}){tail}"


YESTERDAY_LABEL = {"lower_intensity": "Take it easy", "prioritize_sleep": "Earlier night",
                   "recover_between": "Breaks in a busy day", "go_hard": "Hard session"}
OUTCOME_MARK = {"done": "&#10003;", "partly": "&#9680;", "not_done": "&#9675;", "no_data": "&#8211;",
                "unmeasured": "&#8211;"}


def yesterday_text(summary: dict) -> str | None:
    """One line on yesterday's focus, measured from the data. Facts side by side, no causal claim."""
    y = summary.get("yesterday")
    if not y:
        return None
    line = f"{YESTERDAY_LABEL.get(y['focus'], y['title'])}: {y['text']}."
    if y.get("recovery_before") is not None and y.get("recovery_after") is not None:
        line += f" Recovery {y['recovery_before']}% then, {y['recovery_after']}% today."
    return line


def render_text(summary: dict, notices: list[str]) -> str:
    lines = [subject(summary), ""]
    lines += [f"! {n}" for n in notices]
    if yesterday_text(summary):
        lines += [f"YESTERDAY  {yesterday_text(summary)}", ""]
    f = summary.get("focus")
    if f:
        conf = f" ({f['confidence']} confidence)" if f.get("confidence") else ""
        lines += [f"TODAY'S FOCUS: {f['title']}{conf}"]
        if f.get("headline"):
            lines.append(f"  {f['headline']}")
        lines += [f"  - because {r}" for r in f["reasons"]]
        lines += [f"  - on the other hand, {r}" for r in f.get("counter", [])]
        if f.get("block"):
            b = f["block"]
            lines.append(f"  Suggested: {b['start']}-{b['end']}  {b['title']}")
        acts = summary.get("actions") or {}
        if acts:
            lines += [f"  {label}: {acts[k]}" for k, label in ACTION_LABELS if acts.get(k)]
        lines += [f"  {a}" for a in f.get("alternatives", [])]
        if f.get("note"):
            lines.append(f"  {f['note']}")
        if f.get("caveat"):
            lines.append(f"  {f['caveat']}")
        lines.append("")
    if not summary["last_night_scored"]:
        lines.append("Last night's sleep is not scored yet (or WHOOP was not worn).")
    lines.append("Last night")
    for m in summary["metrics"]:
        lines.append(f"  {m['label']:20s} {_fmt(m['value'], m['unit']):>10s}   {_delta(m)}  "
                     f"({STATUS_TEXT[m['status']]})")
    if summary["yesterday_load"] is not None:
        lines.append(f"  {'Yesterday strain':20s} {summary['yesterday_load']:>10g}")
    trends = trend_lines(summary)
    if trends:
        lines += ["", "Trends"] + [f"  {t}" for t, _ in trends]
    cal = summary["calendar"]
    if cal:
        lines += ["", "Today's calendar",
                  f"  {_events(cal['event_count'])}, {cal['busy_hours']:g} busy hours"
                  + (f", {cal['first_start']}-{cal['last_end']}" if cal["first_start"] else "")]
        if cal["free_windows"]:
            lines.append("  Free: " + ", ".join(f"{w['start']}-{w['end']}" for w in cal["free_windows"]))
    return "\n".join(lines)


# ---------- HTML email ----------
# Email clients ignore <style> blocks and modern layout, so everything is inline styles and
# tables. Text stays in ink colors; status colors only mark dots, arrows, pills and the meter,
# always next to a word that says the same thing.

INK, INK_2, MUTED, LINE, PAGE, CARD = "#111827", "#374151", "#6b7280", "#e5e7eb", "#f3f4f6", "#ffffff"
GOOD, WARN, BAD = "#0ca30c", "#fab219", "#d03b3b"
ZONE_STYLE = {  # (meter fill, pill background, label)
    "green": (GOOD, "#e3f5e3", "Green"),
    "yellow": (WARN, "#fef3d6", "Yellow"),
    "red": (BAD, "#fbe3e3", "Red"),
}
FREE, BUSY = "#93c5fd", "#d1d5db"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def _card(inner: str, pad: str = "20px 22px") -> str:
    return (f'<tr><td style="padding:0 0 12px"><table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0" style="background:{CARD};border:1px solid {LINE};border-radius:14px">'
            f'<tr><td style="padding:{pad}">{inner}</td></tr></table></td></tr>')


def _title(text: str) -> str:
    return (f'<div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:{MUTED};'
            f'font-weight:600;margin:0 0 12px">{escape(text)}</div>')


def _arrow(m: dict) -> str:
    if m["delta"] in (None, 0):
        return ""
    color = GOOD if m["status"] == "better" else BAD if m["status"] == "worse" else MUTED
    return f'<span style="color:{color}">{"&#9650;" if m["delta"] > 0 else "&#9660;"}</span> '


def _hero(summary: dict) -> str:
    rec = summary["metrics"][0]
    if rec["value"] is None:
        return _card(f'{_title("Recovery")}<div style="font-size:22px;font-weight:600;color:{INK}">'
                     f'Last night is not scored yet</div><div style="color:{MUTED};margin-top:4px">'
                     'WHOOP may still be processing, or it was not worn.</div>')
    fill, pill_bg, label = ZONE_STYLE.get(summary["recovery_zone"], (MUTED, LINE, "-"))
    pct = max(2, min(100, int(round(rec["value"]))))
    strain = summary.get("yesterday_load")
    side = []
    if rec["delta"] is not None:
        side.append(f'{_arrow(rec)}{escape(_delta(rec))}')
    if strain is not None:
        side.append(f"Yesterday's strain {strain:g}")
    side_html = "<br>".join(side)
    meter = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;'
             f'border-collapse:separate"><tr><td style="background:{pill_bg};border-radius:6px;height:8px;'
             f'font-size:0;line-height:0"><table role="presentation" width="{pct}%" cellpadding="0" cellspacing="0">'
             f'<tr><td style="background:{fill};border-radius:6px;height:8px;font-size:0;line-height:0">&nbsp;'
             f'</td></tr></table></td></tr></table>')
    body = (
        f'{_title("Recovery")}'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="vertical-align:bottom"><span style="font-size:56px;line-height:1;font-weight:600;'
        f'color:{INK}">{rec["value"]:g}</span><span style="font-size:24px;color:{MUTED};font-weight:600">%</span>'
        f'&nbsp;&nbsp;<span style="display:inline-block;vertical-align:middle;background:{pill_bg};color:{INK};'
        f'border-radius:999px;padding:4px 10px;font-size:13px;font-weight:600">'
        f'<span style="color:{fill}">&#9679;</span> {label}</span></td>'
        f'<td style="vertical-align:bottom;text-align:right;color:{INK_2};font-size:14px;line-height:1.5">'
        f'{side_html}</td></tr></table>{meter}'
    )
    return _card(body)


def _metrics(summary: dict) -> str:
    tiles = [m for m in summary["metrics"][1:]]
    cells = []
    for m in tiles:
        sub = (f'{_arrow(m)}{escape(_delta(m))}' if m["delta"] is not None
               else escape(STATUS_TEXT[m["status"]]))
        cells.append(
            f'<td width="50%" style="padding:10px 12px;vertical-align:top;background:#f9fafb;border-radius:10px">'
            f'<div style="font-size:12px;color:{MUTED}">{escape(m["label"])}</div>'
            f'<div style="font-size:20px;font-weight:600;color:{INK};margin:2px 0">'
            f'{escape(_fmt(m["value"], m["unit"]))}</div>'
            f'<div style="font-size:12px;color:{INK_2}">{sub}</div></td>')
    rows = []
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2] + (['<td width="50%"></td>'] if len(cells[i:i + 2]) == 1 else [])
        rows.append(f'<tr>{pair[0]}<td style="width:8px"></td>{pair[1]}</tr>'
                    f'<tr><td colspan="3" style="height:8px;font-size:0;line-height:0">&nbsp;</td></tr>')
    grid = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(rows)}</table>')
    return _card(f'{_title("Last night")}{grid}', pad="20px 22px 12px")


CHART_H = 56


def _hrv_chart(sig: dict) -> str:
    """14-day HRV bars as an email-safe table (no SVG or JS, which mail clients block).
    Bars below your normal range are red, above it green, otherwise gray; the caption says
    the same in words, so color is never the only cue."""
    series = sig.get("hrv_daily") or []
    vals = [p["value"] for p in series if p["value"] is not None]
    if len(vals) < 5:
        return ""
    band = sig.get("hrv")
    lo_ref = min(vals + ([band["normal_low"]] if band else []))
    hi_ref = max(vals + ([band["normal_high"]] if band else []))
    pad = max(1.0, (hi_ref - lo_ref) * 0.15)
    ymin, ymax = lo_ref - pad, hi_ref + pad
    cells = []
    last = len(series) - 1
    for i, p in enumerate(series):
        v = p["value"]
        if v is None:
            bar = f'<div style="height:2px;background:{LINE};font-size:0;line-height:0">&nbsp;</div>'
        else:
            h = max(3, int(round((v - ymin) / (ymax - ymin) * CHART_H)))
            color = "#9ca3af"
            if band and v < band["normal_low"]:
                color = BAD
            elif band and v > band["normal_high"]:
                color = GOOD
            if i == last and color == "#9ca3af":
                color = INK_2  # emphasize the latest night
            bar = (f'<div title="{p["day"]}: {v:g} ms" style="height:{h}px;background:{color};'
                   f'border-radius:3px 3px 0 0;font-size:0;line-height:0">&nbsp;</div>')
        cells.append(f'<td style="vertical-align:bottom;height:{CHART_H}px;padding:0 2px">{bar}</td>')
    first_day, last_day = series[0]["day"][5:], series[-1]["day"][5:]
    latest = next((p["value"] for p in reversed(series) if p["value"] is not None), None)
    caption = "HRV, last 14 nights (ms)"
    if band:
        caption += f". Red: below your normal range ({band['normal_low']:g}-{band['normal_high']:g})"
    return (f'<div style="font-size:12px;color:{MUTED};margin-bottom:6px">{escape(caption)}</div>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="table-layout:fixed;border-bottom:1px solid {LINE}"><tr>{"".join(cells)}</tr></table>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="font-size:11px;color:{MUTED};padding-top:3px">{first_day}</td>'
            f'<td style="font-size:11px;color:{MUTED};padding-top:3px;text-align:right">{last_day}'
            f'{f" &middot; {latest:g} ms" if latest is not None else ""}</td></tr></table>'
            f'<div style="height:12px;font-size:0;line-height:0">&nbsp;</div>')


def _trends(summary: dict) -> str:
    lines = trend_lines(summary)
    chart = _hrv_chart(summary.get("signals") or {})
    if not lines and not chart:
        return ""
    dot = {"good": GOOD, "bad": BAD, "neutral": "#9ca3af"}
    rows = "".join(
        f'<tr><td style="width:18px;vertical-align:top;padding:5px 0;color:{dot[tone]};font-size:12px">&#9679;</td>'
        f'<td style="padding:4px 0;color:{INK_2};font-size:14px;line-height:1.45">{escape(text)}</td></tr>'
        for text, tone in lines)
    return _card(f'{_title("Trends")}{chart}<table role="presentation" width="100%" cellpadding="0" '
                 f'cellspacing="0">{rows}</table>')


def _today(summary: dict) -> str:
    cal = summary.get("calendar")
    if not cal:
        return ""
    span = f" &middot; {cal['first_start']}-{cal['last_end']}" if cal["first_start"] else ""
    head = (f'<div style="font-size:15px;color:{INK};font-weight:600">{_events(cal["event_count"])} &middot; '
            f'{cal["busy_hours"]:g} busy hours{span}</div>')
    bar = ""
    if cal.get("timeline"):
        segs = "".join(
            f'<td width="{max(0.5, seg["share"] * 100):.2f}%" title="{seg["start"]}-{seg["end"]}" '
            f'style="background:{FREE if seg["kind"] == "free" else BUSY};height:14px;font-size:0;line-height:0;'
            f'border-right:2px solid {CARD}">&nbsp;</td>'
            for seg in cal["timeline"])
        ticks = "".join(f'<td width="25%" style="font-size:11px;color:{MUTED};padding-top:4px">{t}</td>'
                        for t in ("08:00", "11:00", "14:00", "17:00"))
        bar = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;'
               f'border-radius:6px;overflow:hidden"><tr>{segs}</tr></table>'
               f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{ticks}'
               f'</tr></table>'
               f'<div style="font-size:12px;color:{MUTED};margin-top:6px">'
               f'<span style="color:{FREE}">&#9632;</span> Free &nbsp; <span style="color:{BUSY}">&#9632;</span> Busy'
               f' &nbsp;(08:00-20:00)</div>')
    pills = "".join(
        f'<span style="display:inline-block;margin:8px 6px 0 0;padding:4px 10px;border-radius:999px;'
        f'background:#eff6ff;color:{INK};font-size:13px">{w["start"]}-{w["end"]}</span>'
        for w in cal["free_windows"])
    free = (f'<div style="margin-top:12px;font-size:13px;color:{INK_2}">Free from now on:</div>{pills}'
            if pills else f'<div style="margin-top:12px;font-size:13px;color:{INK_2}">No free blocks left today.</div>')
    return _card(f'{_title("Today")}{head}{bar}{free}')


FOCUS_ACCENT = {"lower_intensity": "#f59e0b", "prioritize_sleep": "#6366f1", "recover_between": "#14b8a6",
                "go_hard": GOOD, "none": "#9ca3af"}


CONFIDENCE_LABEL = {"high": "High confidence", "moderate": "Moderate confidence", "tentative": "Tentative"}
CONFIDENCE_DOTS = {"high": 3, "moderate": 2, "tentative": 1}


def _bullets(items: list[str], color: str) -> str:
    rows = "".join(
        f'<tr><td style="width:14px;vertical-align:top;color:{MUTED};padding:3px 0">&middot;</td>'
        f'<td style="color:{color};font-size:14px;line-height:1.45;padding:3px 0">'
        f'{escape(r[:1].upper() + r[1:])}</td></tr>' for r in items)
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>'


def _label(text: str, top: int = 12) -> str:
    return f'<div style="font-size:12px;color:{MUTED};margin:{top}px 0 2px">{escape(text)}</div>'


def _focus(summary: dict) -> str:
    f = summary.get("focus")
    if not f:
        return ""
    accent = FOCUS_ACCENT.get(f["focus"], "#9ca3af")
    chip = ""
    if f.get("confidence"):
        n = CONFIDENCE_DOTS[f["confidence"]]
        dots = (f'<span style="color:{INK}">{"&#9679;" * n}</span>'
                f'<span style="color:{LINE}">{"&#9679;" * (3 - n)}</span>')
        chip = (f'<span style="display:inline-block;margin-left:8px;vertical-align:middle;background:#f3f4f6;'
                f'border-radius:999px;padding:3px 9px;font-size:12px;color:{INK_2};font-weight:500">'
                f'{dots}&nbsp; {CONFIDENCE_LABEL[f["confidence"]]}</span>')
    headline = (f'<div style="font-size:15px;color:{INK_2};margin-top:6px">{escape(f["headline"])}</div>'
                if f.get("headline") else "")
    why = (_label("Why") + _bullets(f["reasons"], INK_2)) if f.get("reasons") else ""
    other = (_label("Pointing the other way") + _bullets(f["counter"], MUTED)) if f.get("counter") else ""
    block_html = ""
    if f.get("block"):
        b = f["block"]
        block_html = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:14px">'
                      f'<tr><td style="background:#f9fafb;border:1px solid {LINE};border-radius:10px;'
                      f'padding:10px 14px">'
                      f'<span style="font-size:15px;font-weight:600;color:{INK}">{b["start"]}-{b["end"]}</span>'
                      f'<span style="color:{MUTED}"> &nbsp;&middot;&nbsp; </span>'
                      f'<span style="font-size:14px;color:{INK_2}">{escape(b["title"])}</span></td></tr></table>')
    actions_html = _action_buttons(summary.get("actions"))
    small = [x for x in [*f.get("alternatives", []), f.get("note"), f.get("caveat")] if x]
    small_html = "".join(f'<div style="font-size:13px;color:{MUTED};margin-top:8px;line-height:1.45">'
                         f'{escape(x)}</div>' for x in small)
    if small_html:
        small_html = f'<div style="margin-top:6px">{small_html}</div>'
    focus_title = _title("Today's focus")
    body = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="width:4px;background:{accent};border-radius:4px"></td><td style="padding-left:16px">'
            f'{focus_title}'
            f'<div style="font-size:22px;font-weight:600;color:{INK};line-height:1.25">{escape(f["title"])}{chip}</div>'
            f'{headline}{why}{other}{block_html}{actions_html}{small_html}</td></tr></table>')
    return _card(body)


ACTION_LABELS = (("add", "Add to calendar"), ("change", "Change time"), ("dismiss", "Dismiss"),
                 ("not_useful", "Not useful?"))


def _action_buttons(actions: dict | None) -> str:
    """Optional actions. Ignoring the email is a perfectly fine response, so the buttons stay
    small: Add to calendar and Change time, then a quiet text link (Dismiss or Not useful?)."""
    if not actions:
        return ""
    buttons = [(k, label, bg, fg, border) for (k, label), (bg, fg, border) in
               zip(ACTION_LABELS[:2], ((INK, "#ffffff", INK), (CARD, INK, LINE))) if actions.get(k)]
    cells = "".join(
        f'<td style="padding:0 8px 0 0"><a href="{escape(actions[key])}" style="display:inline-block;'
        f'background:{bg};color:{fg};border:1px solid {border};border-radius:10px;padding:9px 16px;'
        f'font-size:14px;font-weight:600;text-decoration:none">{label}</a></td>'
        for key, label, bg, fg, border in buttons)
    quiet = [(k, label) for k, label in ACTION_LABELS[2:] if actions.get(k)]
    quiet_html = " &nbsp;&middot;&nbsp; ".join(
        f'<a href="{escape(actions[k])}" style="color:{MUTED};text-decoration:underline">{label}</a>'
        for k, label in quiet)
    html = ""
    if cells:
        html += (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:12px"><tr>{cells}'
                 f'</tr></table>')
    note = "Adds it to your Recovery Lab calendar with a reminder; you can undo it." if cells else ""
    line = " &nbsp;&middot;&nbsp; ".join(x for x in (note, quiet_html) if x)
    if line:
        html += f'<div style="font-size:12px;color:{MUTED};margin-top:8px">{line}</div>'
    return html


def _yesterday(summary: dict) -> str:
    y = summary.get("yesterday")
    text = yesterday_text(summary)
    if not y or not text:
        return ""
    mark = OUTCOME_MARK.get(y["outcome"], "&#8211;")
    color = GOOD if y["outcome"] == "done" else MUTED
    return _card(f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
                 f'<td style="vertical-align:top;padding-right:10px;color:{color};font-size:16px">{mark}</td>'
                 f'<td style="font-size:14px;color:{INK_2};line-height:1.45">'
                 f'<span style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:{MUTED};'
                 f'font-weight:600">Yesterday</span>&nbsp; {escape(text)}</td></tr></table>', pad="14px 18px")


def render_html(summary: dict, notices: list[str]) -> str:
    notice_html = "".join(
        f'<tr><td style="padding:0 0 12px"><div style="background:#fef3d6;border:1px solid #f7d58a;'
        f'border-radius:12px;padding:12px 16px;color:{INK};font-size:14px">&#9888; {escape(n)}</div></td></tr>'
        for n in notices)
    header = (f'<tr><td style="padding:0 4px 14px"><table role="presentation" width="100%" cellpadding="0" '
              f'cellspacing="0"><tr><td style="font-size:13px;font-weight:700;letter-spacing:.08em;color:{INK}">'
              f'RECOVERY LAB</td><td style="text-align:right;font-size:13px;color:{MUTED}">'
              f'{escape(summary["weekday"])}, {escape(summary["date"])}</td></tr></table></td></tr>')
    footer = (f'<tr><td style="padding:8px 4px 0;font-size:12px;color:{MUTED};line-height:1.5">'
              f'Compared with your own recent history. The focus is chosen by transparent rules, not '
              f'experiment results; a single day cannot show what caused what. Not medical advice. '
              f'Change the delivery time with <code>make settings</code>.</td></tr>')
    content = (header + notice_html + _hero(summary) + _yesterday(summary) + _focus(summary) + _metrics(summary)
               + _trends(summary) + _today(summary) + footer)
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"></head>'
            f'<body style="margin:0;padding:0;background:{PAGE}">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE};'
            f'font-family:{FONT}"><tr><td align="center" style="padding:24px 12px">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px">'
            f'{content}</table></td></tr></table></body></html>')


def render_email(summary: dict, notices: list[str] | None = None) -> tuple[str, str, str]:
    notices = notices or []
    return subject(summary), render_html(summary, notices), render_text(summary, notices)
