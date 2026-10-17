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


TONE_COLORS = {"good": "#16a34a", "bad": "#dc2626", "neutral": "#374151"}


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

    trends = trend_lines(summary)
    if trends:
        items = "".join(f'<li style="color:{TONE_COLORS[tone]};margin:2px 0">{escape(t)}</li>' for t, tone in trends)
        parts.append('<h3 style="margin-bottom:4px">Trends</h3>'
                     f'<ul style="margin-top:0;padding-left:18px">{items}</ul>')

    cal = summary["calendar"]
    if cal:
        span = f" · {cal['first_start']}-{cal['last_end']}" if cal["first_start"] else ""
        free = ", ".join(f"{w['start']}-{w['end']}" for w in cal["free_windows"]) or "none"
        parts.append(f'<h3 style="margin-bottom:4px">Today</h3><p style="margin:0">{_events(cal["event_count"])} · '
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
