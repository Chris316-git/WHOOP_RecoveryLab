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
    return f"{head} · Recovery {rec:g}% ({summary['recovery_zone']})"


def render_text(summary: dict, notices: list[str]) -> str:
    lines = [subject(summary), ""]
    lines += [f"! {n}" for n in notices]
    if not summary["last_night_scored"]:
        lines.append("Last night's sleep is not scored yet (or WHOOP was not worn).")
    lines.append("Last night")
    for m in summary["metrics"]:
        lines.append(f"  {m['label']:20s} {_fmt(m['value'], m['unit']):>10s}   {_delta(m)}  "
                     f"({STATUS_TEXT[m['status']]})")
    if summary["yesterday_strain"] is not None:
        lines.append(f"  {'Yesterday strain':20s} {summary['yesterday_strain']:>10g}")
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
    if summary["suggestions"]:
        lines += ["", "Suggestions (rule-based, not experiment results)"]
        lines += [f"  - {s}" for s in summary["suggestions"]]
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
    strain = summary.get("yesterday_strain")
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


def _trends(summary: dict) -> str:
    lines = trend_lines(summary)
    if not lines:
        return ""
    dot = {"good": GOOD, "bad": BAD, "neutral": "#9ca3af"}
    rows = "".join(
        f'<tr><td style="width:18px;vertical-align:top;padding:5px 0;color:{dot[tone]};font-size:12px">&#9679;</td>'
        f'<td style="padding:4px 0;color:{INK_2};font-size:14px;line-height:1.45">{escape(text)}</td></tr>'
        for text, tone in lines)
    return _card(f'{_title("Trends")}<table role="presentation" width="100%" cellpadding="0" '
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


def _suggestions(summary: dict) -> str:
    if not summary["suggestions"]:
        return ""
    items = "".join(f'<tr><td style="padding:4px 0;color:{INK};font-size:14px;line-height:1.5">{escape(s)}</td></tr>'
                    for s in summary["suggestions"])
    return _card(f'{_title("Suggestions")}<table role="presentation" width="100%" cellpadding="0" '
                 f'cellspacing="0" style="border-left:3px solid {INK};padding-left:12px"><tr><td>'
                 f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{items}</table>'
                 f'</td></tr></table><div style="font-size:12px;color:{MUTED};margin-top:10px">Rule-based hints from '
                 f'WHOOP zones and your own baseline, not experiment results.</div>')


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
              f'Compared with your own recent history. Not medical advice. '
              f'Change the delivery time with <code>make settings</code>.</td></tr>')
    content = (header + notice_html + _hero(summary) + _metrics(summary) + _trends(summary)
               + _today(summary) + _suggestions(summary) + footer)
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
