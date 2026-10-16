"""Turn a daily summary into an email (subject, HTML, plain text). Formatting only."""
from html import escape

ZONE_COLORS = {"green": "#16a34a", "yellow": "#ca8a04", "red": "#dc2626"}
STATUS_TEXT = {"better": "better than usual", "worse": "worse than usual", "typical": "typical",
               "no_baseline": "building baseline", "no_data": "no data"}
STATUS_COLORS = {"better": "#16a34a", "worse": "#dc2626"}


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
    for key, t in summary["week_trend"].items():
        label = "Recovery" if key == "recovery_score" else "HRV"
        lines.append(f"7-day {label}: {t['week_mean']:g} (30-day median {t['baseline_median']:g})")
    cal = summary["calendar"]
    if cal:
        lines += ["", "Today's calendar",
                  f"  {cal['event_count']} events, {cal['busy_hours']:g} busy hours"
                  + (f", {cal['first_start']}-{cal['last_end']}" if cal["first_start"] else "")]
        if cal["free_windows"]:
            lines.append("  Free: " + ", ".join(f"{w['start']}-{w['end']}" for w in cal["free_windows"]))
    if summary["suggestions"]:
        lines += ["", "Suggestions (rule-based, not experiment results)"]
        lines += [f"  - {s}" for s in summary["suggestions"]]
    return "\n".join(lines)


def render_html(summary: dict, notices: list[str]) -> str:
    zone = summary["recovery_zone"]
    color = ZONE_COLORS.get(zone, "#6b7280")
    rec = summary["metrics"][0]
    parts = [
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:560px;'
        'margin:0 auto;color:#111827">',
        f'<p style="color:#6b7280;margin:0">{escape(summary["weekday"])} · {escape(summary["date"])}</p>',
    ]
    for n in notices:
        parts.append(f'<p style="background:#fef3c7;padding:8px 12px;border-radius:6px">{escape(n)}</p>')
    if rec["value"] is not None:
        parts.append(f'<h1 style="margin:8px 0 4px;font-size:40px;color:{color}">{rec["value"]:g}%</h1>'
                     f'<p style="margin:0 0 16px">Recovery · <b style="color:{color}">{escape(zone or "")}</b>'
                     f' · {escape(_delta(rec))}</p>')
    else:
        parts.append('<h2>Last night is not scored yet</h2>')

    rows = []
    for m in summary["metrics"][1:]:
        st = m["status"]
        rows.append(
            f'<tr><td style="padding:6px 0">{escape(m["label"])}</td>'
            f'<td style="padding:6px 8px;text-align:right"><b>{escape(_fmt(m["value"], m["unit"]))}</b></td>'
            f'<td style="padding:6px 0;color:{STATUS_COLORS.get(st, "#6b7280")}">'
            f'{escape(_delta(m) or STATUS_TEXT[st])}</td></tr>')
    if summary["yesterday_strain"] is not None:
        rows.append(f'<tr><td style="padding:6px 0">Yesterday strain</td><td style="padding:6px 8px;'
                    f'text-align:right"><b>{summary["yesterday_strain"]:g}</b></td><td></td></tr>')
    parts.append('<table style="width:100%;border-collapse:collapse;font-size:15px">' + "".join(rows) + "</table>")

    if summary["week_trend"]:
        items = []
        for key, t in summary["week_trend"].items():
            label = "Recovery" if key == "recovery_score" else "HRV"
            items.append(f"{label} {t['week_mean']:g} (usual {t['baseline_median']:g})")
        parts.append(f'<p style="color:#374151">Last 7 days: {escape(" · ".join(items))}</p>')

    cal = summary["calendar"]
    if cal:
        span = f" · {cal['first_start']}-{cal['last_end']}" if cal["first_start"] else ""
        free = ", ".join(f"{w['start']}-{w['end']}" for w in cal["free_windows"]) or "none"
        parts.append(f'<h3 style="margin-bottom:4px">Today</h3><p style="margin:0">{cal["event_count"]} events · '
                     f'{cal["busy_hours"]:g} busy hours{escape(span)}<br>Free blocks: {escape(free)}</p>')
    if summary["suggestions"]:
        tips = "".join(f"<li>{escape(s)}</li>" for s in summary["suggestions"])
        parts.append(f'<h3 style="margin-bottom:4px">Suggestions</h3><ul style="margin-top:0">{tips}</ul>'
                     '<p style="color:#9ca3af;font-size:12px">Rule-based hints from WHOOP zones and your own '
                     '30-day baseline, not experiment results. Not medical advice.</p>')
    parts.append("</div>")
    return "".join(parts)


def render_email(summary: dict, notices: list[str] | None = None) -> tuple[str, str, str]:
    notices = notices or []
    return subject(summary), render_html(summary, notices), render_text(summary, notices)
