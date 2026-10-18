#!/usr/bin/env python3
"""
Have the cats been fed?
A shared log so housemates can mark the cat's meals, with feeding times and a
status light that warns when a meal is due or overdue.

Open it on any phone/laptop on the home wifi (or over Tailscale when away).
Edit HOUSEMATES and CATS below. Feeding times are set in the Settings page.
"""

import sqlite3
import os
import calendar as calmod
from html import escape
from datetime import date, datetime, timedelta
from flask import Flask, request, redirect, url_for, g, jsonify

# ---- Edit these ----
HOUSEMATES = ["Tee", "Dan", "Cole", "Liv", "Guest"]   # who can log a feed
CATS = ["Goobie & Coco"]                # both cats fed together under one entry
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feeds.db")
# --------------------

# Meal name -> settings key for its time
MEALS = [("Morning", "morning_time"), ("Evening", "evening_time")]
DEFAULTS = {"morning_time": "08:00", "evening_time": "18:00", "warn_minutes": "60"}

# Lateness thresholds for the history calendar (minutes after the scheduled time)
LATE_GRACE_MIN = 30    # fed within this many minutes = on time (green)
VERY_LATE_MIN = 120    # fed within this many minutes = late (amber); beyond = very late (red)

HOT_STREAK_DAYS = 3    # a person's streak becomes "hot" at this many days in a row

app = Flask(__name__)


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL, cat TEXT NOT NULL, meal TEXT NOT NULL,
            fed_by TEXT NOT NULL, fed_at TEXT NOT NULL,
            UNIQUE(day, cat, meal)
        )""")
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    for k, v in DEFAULTS.items():
        con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
    con.commit()
    con.close()


def get_setting(key):
    row = db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else DEFAULTS.get(key, "")


def todays_feeds():
    today = date.today().isoformat()
    rows = db().execute(
        "SELECT cat, meal, fed_by, fed_at FROM feeds WHERE day=?", (today,)
    ).fetchall()
    return today, {(r["cat"], r["meal"]): r for r in rows}


def meal_status(meal_key, fed_rec):
    """Return (state, label) for a meal. state in done/upcoming/soon/overdue."""
    if fed_rec:
        t = datetime.fromisoformat(fed_rec["fed_at"]).strftime("%H:%M")
        return "done", f"Fed by {fed_rec['fed_by']} at {t}"
    now = datetime.now()
    try:
        hh, mm = (int(x) for x in get_setting(meal_key).split(":"))
        sched = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    except ValueError:
        return "upcoming", "No valid time set"
    warn = int(get_setting("warn_minutes") or 60)
    if now < sched - timedelta(minutes=warn):
        return "upcoming", f"Due at {sched.strftime('%H:%M')}"
    if now < sched:
        mins = int((sched - now).total_seconds() // 60)
        return "soon", f"Due in {mins} min"
    mins = int((now - sched).total_seconds() // 60)
    late = f"{mins} min" if mins < 60 else f"{mins // 60}h {mins % 60}m"
    return "overdue", f"Overdue by {late}"


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Cat feeding log</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f4f4f5; --text: #18181b; --muted: #71717a;
    --card: #ffffff; --border: #d4d4d8; --th: #fafafa; --link: #2563eb;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #18181b; --text: #f4f4f5; --muted: #a1a1aa;
      --card: #27272a; --border: #3f3f46; --th: #3f3f46; --link: #60a5fa;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0;
         background: var(--bg); color: var(--text); }}
  .wrap {{ max-width: 540px; margin: 0 auto; padding: 16px; }}
  header {{ display: flex; justify-content: space-between; align-items: baseline; }}
  h1 {{ font-size: 1.35rem; margin: 12px 0 2px; }}
  a.link {{ color: var(--link); text-decoration: none; font-size: .95rem; }}
  .date {{ color: var(--muted); margin-bottom: 16px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px;
           padding: 16px; margin-bottom: 12px; display: flex; align-items: center; gap: 14px; }}
  .dot {{ width: 20px; height: 20px; border-radius: 50%; flex-shrink: 0; }}
  .done     {{ background: #16a34a; }}
  .upcoming {{ background: #a1a1aa; }}
  .soon     {{ background: #d97706; animation: pulse-amber 1.6s infinite; }}
  .overdue  {{ background: #dc2626; animation: pulse-red 1s infinite; }}
  @keyframes pulse-amber {{
    0%,100% {{ box-shadow: 0 0 0 0 rgba(217,119,6,.7); }}
    50% {{ box-shadow: 0 0 0 8px rgba(217,119,6,0); }} }}
  @keyframes pulse-red {{
    0%,100% {{ box-shadow: 0 0 0 0 rgba(220,38,38,.7); }}
    50% {{ box-shadow: 0 0 0 10px rgba(220,38,38,0); }} }}
  .meal {{ flex: 1; }}
  .meal-name {{ font-weight: 600; font-size: 1.1rem; }}
  .meal-sub {{ color: var(--muted); font-size: .9rem; margin-top: 2px; }}
  .overdue-text {{ color: #ef4444; font-weight: 600; font-size: .9rem; margin-top: 2px; }}
  form.inline {{ display: flex; gap: 8px; }}
  select, input {{ padding: 9px; border-radius: 10px; border: 1px solid var(--border);
                   font-size: 1rem; background: var(--card); color: var(--text); }}
  button {{ padding: 9px 14px; border: none; border-radius: 10px; font-size: 1rem; font-weight: 600; cursor: pointer; }}
  .feed-btn {{ background: #16a34a; color: #fff; }}
  .undo-btn {{ background: transparent; color: var(--muted); text-decoration: underline; padding: 4px 0; font-size:.9rem; }}
  label {{ display:block; margin: 12px 0 4px; font-weight:600; }}
  input {{ width: 160px; }}
  .ghwrap {{ overflow-x:auto; padding-bottom:2px; }}
  .ghgrid {{ display:grid; grid-auto-flow:column; grid-template-rows:repeat(7, 12px); gap:3px; width:max-content; padding-right:4px; }}
  .gd {{ width:12px; height:12px; border-radius:2px; background:var(--border); opacity:.35; }}
  .gd.pending {{ opacity:1; }}
  .gd.ontime {{ background:#16a34a; opacity:1; }}
  .gd.late {{ background:#d97706; opacity:1; }}
  .gd.vlate {{ background:#dc2626; opacity:1; }}
  .gd.missed {{ background:#7f1d1d; opacity:1; }}
  .key {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; font-size:.72rem; color:var(--muted); }}
  .key span {{ display:flex; align-items:center; gap:5px; }}
  .key i {{ width:11px; height:11px; border-radius:2px; display:inline-block; }}
  .cardtitle {{ font-size:1.05rem; font-weight:600; margin:0 0 10px; }}
  .lbrow {{ display:flex; align-items:center; gap:10px; padding:7px 0; border-bottom:1px solid var(--border); }}
  .lbrow:last-child {{ border-bottom:none; }}
  .lbrank {{ width:16px; color:var(--muted); font-size:.85rem; text-align:right; }}
  .lbname {{ min-width:52px; font-weight:600; }}
  .lbbar {{ flex:1; height:8px; background:var(--border); border-radius:4px; overflow:hidden; }}
  .lbbar span {{ display:block; height:100%; background:#16a34a; }}
  .lbcount {{ width:26px; text-align:right; font-variant-numeric:tabular-nums; }}
  .hot {{ background:#dc2626; color:#fff; font-size:.66rem; font-weight:700; padding:2px 7px;
          border-radius:999px; letter-spacing:.03em; white-space:nowrap; }}
  .streak {{ color:var(--muted); font-size:.72rem; white-space:nowrap; }}
</style>
</head>
<body>
<div class="wrap">{body}</div>
<script>
  document.querySelectorAll('.ghwrap').forEach(function(e){{ e.scrollLeft = e.scrollWidth; }});
</script>
</body>
</html>"""


def home_body():
    today, done = todays_feeds()
    nice = datetime.now().strftime("%A %d %B %Y")
    cards = ""
    for cat in CATS:
        for name, key in MEALS:
            rec = done.get((cat, name))
            state, label = meal_status(key, rec)
            title = escape(name + (f" - {cat}" if len(CATS) > 1 else ""))
            sub_cls = "overdue-text" if state == "overdue" else "meal-sub"
            ecat, ename = escape(cat, quote=True), escape(name, quote=True)
            if rec:
                action = (
                    f'<form class="inline" method="post" action="/undo">'
                    f'<input type="hidden" name="cat" value="{ecat}">'
                    f'<input type="hidden" name="meal" value="{ename}">'
                    f'<button class="undo-btn" type="submit">undo</button></form>'
                )
            else:
                opts = "".join(
                    f'<option value="{escape(h, quote=True)}">{escape(h)}</option>'
                    for h in HOUSEMATES
                )
                action = (
                    f'<form class="inline" method="post" action="/feed">'
                    f'<input type="hidden" name="cat" value="{ecat}">'
                    f'<input type="hidden" name="meal" value="{ename}">'
                    f'<select name="fed_by" required>{opts}</select>'
                    f'<button class="feed-btn" type="submit">Mark fed</button></form>'
                )
            cards += (
                f'<div class="card"><div class="dot {state}"></div>'
                f'<div class="meal"><div class="meal-name">{title}</div>'
                f'<div class="{sub_cls}">{label}</div></div>{action}</div>'
            )
    return (
        f'<header><h1>Cat feeding log</h1>'
        f'<a class="link" href="/settings">Settings</a></header>'
        f'<div class="date">{nice}</div>{cards}'
        f'{calendar_card()}'
        f'{leaderboard_card()}'
    )


@app.route("/")
def index():
    return PAGE.format(body=home_body())


@app.route("/feed", methods=["POST"])
def feed():
    cat, meal, fed_by = request.form["cat"], request.form["meal"], request.form["fed_by"]
    names = [m[0] for m in MEALS]
    if cat in CATS and meal in names and fed_by in HOUSEMATES:
        try:
            db().execute(
                "INSERT INTO feeds (day, cat, meal, fed_by, fed_at) VALUES (?,?,?,?,?)",
                (date.today().isoformat(), cat, meal, fed_by, datetime.now().isoformat()),
            )
            db().commit()
        except sqlite3.IntegrityError:
            pass
    return redirect(url_for("index"))


@app.route("/undo", methods=["POST"])
def undo():
    db().execute(
        "DELETE FROM feeds WHERE day=? AND cat=? AND meal=?",
        (date.today().isoformat(), request.form["cat"], request.form["meal"]),
    )
    db().commit()
    return redirect(url_for("index"))


def status_payload():
    """Compact machine-readable snapshot of today's meals, for the CYD screen."""
    today, done = todays_feeds()
    meals = []
    for cat in CATS:
        for name, key in MEALS:
            rec = done.get((cat, name))
            state, label = meal_status(key, rec)
            meals.append({
                "cat": cat, "meal": name, "state": state, "label": label,
                "fed": bool(rec),
                "fed_by": rec["fed_by"] if rec else None,
            })
    return {"date": today, "cats": CATS, "housemates": HOUSEMATES, "meals": meals}


@app.route("/api/status")
def api_status():
    return jsonify(status_payload())


@app.route("/api/feed", methods=["POST"])
def api_feed():
    """Log a feed from the CYD (or anything). Accepts JSON or form: cat?, meal, fed_by."""
    data = request.get_json(silent=True) or request.form
    cat = data.get("cat") or (CATS[0] if CATS else "")
    meal = data.get("meal")
    fed_by = data.get("fed_by")
    names = [m[0] for m in MEALS]
    if cat in CATS and meal in names and fed_by in HOUSEMATES:
        try:
            db().execute(
                "INSERT INTO feeds (day, cat, meal, fed_by, fed_at) VALUES (?,?,?,?,?)",
                (date.today().isoformat(), cat, meal, fed_by, datetime.now().isoformat()),
            )
            db().commit()
        except sqlite3.IntegrityError:
            pass  # already fed this meal today
        return jsonify(status_payload())
    return jsonify({"error": "bad request", "expected": {"meal": names, "fed_by": HOUSEMATES}}), 400


def feed_state(day_iso, meal_key, rec, today_iso):
    """Status of one meal on one day: ontime/late/vlate/missed/pending/none + label."""
    if rec:
        fed = datetime.fromisoformat(rec["fed_at"])
        try:
            hh, mm = (int(x) for x in get_setting(meal_key).split(":"))
            sched = fed.replace(hour=hh, minute=mm, second=0, microsecond=0)
            delta = (fed - sched).total_seconds() / 60
        except ValueError:
            return "ontime", f"Fed {fed.strftime('%H:%M')}"
        t = fed.strftime("%H:%M")
        by = rec["fed_by"]
        if delta <= LATE_GRACE_MIN:
            return "ontime", f"On time, {t} by {by}"
        if delta <= VERY_LATE_MIN:
            return "late", f"Late, {t} by {by}"
        return "vlate", f"Very late, {t} by {by}"
    if day_iso < today_iso:
        return "missed", "Missed"
    if day_iso == today_iso:
        return "pending", "Not fed yet"
    return "none", ""


def day_status(day_iso, by, today_iso):
    """Combine a day's meals into one colour. Worst meal wins; missed is most severe."""
    sev = {"ontime": 1, "late": 2, "vlate": 3, "missed": 4}
    ranks, pending = [], False
    for name, key in MEALS:
        state, _ = feed_state(day_iso, key, by.get((day_iso, name)), today_iso)
        if state in sev:
            ranks.append(sev[state])
        elif state == "pending":
            pending = True
    if ranks:
        return {1: "ontime", 2: "late", 3: "vlate", 4: "missed"}[max(ranks)]
    return "pending" if pending else "none"


def day_tip(day_iso, by, today_iso):
    parts = [datetime.fromisoformat(day_iso).strftime("%a %d %b")]
    for name, key in MEALS:
        _, label = feed_state(day_iso, key, by.get((day_iso, name)), today_iso)
        if label:
            parts.append(f"{name}: {label}")
    return "  |  ".join(parts)


def current_streak(dayset, today):
    """Consecutive days (ending today, or yesterday if not fed today) this person fed."""
    if today.isoformat() in dayset:
        anchor = today
    elif (today - timedelta(days=1)).isoformat() in dayset:
        anchor = today - timedelta(days=1)
    else:
        return 0
    n, d = 0, anchor
    while d.isoformat() in dayset:
        n += 1
        d -= timedelta(days=1)
    return n


def leaderboard_card():
    today = date.today()
    counts = {r["fed_by"]: r["c"] for r in db().execute(
        "SELECT fed_by, COUNT(*) AS c FROM feeds GROUP BY fed_by").fetchall()}
    days_by = {}
    for r in db().execute("SELECT DISTINCT fed_by, day FROM feeds").fetchall():
        days_by.setdefault(r["fed_by"], set()).add(r["day"])

    board = [(p, counts.get(p, 0), current_streak(days_by.get(p, set()), today))
             for p in HOUSEMATES]
    board.sort(key=lambda x: (-x[1], -x[2], x[0]))
    maxc = max([c for _, c, _ in board] + [1])

    rows_html = ""
    for i, (person, cnt, streak) in enumerate(board, 1):
        if streak >= HOT_STREAK_DAYS:
            badge = f'<span class="hot">HOT {streak}</span>'
        else:
            badge = ""
        barw = int(round(cnt / maxc * 100))
        rows_html += (
            f'<div class="lbrow"><span class="lbrank">{i}</span>'
            f'<span class="lbname">{escape(person)}</span>'
            f'<span class="lbbar"><span style="width:{barw}%"></span></span>'
            f'<span class="lbcount">{cnt}</span>{badge}</div>'
        )
    return (f'<div class="card" style="display:block">'
            f'<div class="cardtitle">Leaderboard</div>{rows_html}</div>')


def calendar_card(weeks=26):
    """GitHub-contributions-style grid: 7 weekday rows x `weeks` columns, ending today."""
    today = date.today()
    today_iso = today.isoformat()
    start_sunday = today - timedelta(days=(today.weekday() + 1) % 7)   # Sunday of this week
    grid_start = start_sunday - timedelta(weeks=weeks - 1)

    rows = db().execute(
        "SELECT day, meal, fed_by, fed_at FROM feeds WHERE day BETWEEN ? AND ?",
        (grid_start.isoformat(), today_iso),
    ).fetchall()
    by = {(r["day"], r["meal"]): r for r in rows}
    mn = db().execute("SELECT MIN(day) AS m FROM feeds").fetchone()
    active_from = mn["m"] if mn and mn["m"] else today_iso   # don't mark pre-start days as missed

    cells = ""
    for w in range(weeks):
        for d in range(7):
            day = grid_start + timedelta(weeks=w, days=d)
            di = day.isoformat()
            if day > today or di < active_from:
                cells += f'<div class="gd" title="{day.strftime("%a %d %b")}"></div>'
            else:
                state = day_status(di, by, today_iso)
                cells += f'<div class="gd {state}" title="{escape(day_tip(di, by, today_iso))}"></div>'

    key = (
        '<div class="key">'
        '<span><i style="background:#16a34a"></i>On time</span>'
        '<span><i style="background:#d97706"></i>Late</span>'
        '<span><i style="background:#dc2626"></i>Very late</span>'
        '<span><i style="background:#7f1d1d"></i>Missed</span>'
        '<span><i style="background:var(--border)"></i>Not yet</span>'
        '</div>'
    )
    return (
        '<div class="card" style="display:block">'
        f'<div class="ghwrap"><div class="ghgrid">{cells}</div></div>'
        f'{key}</div>'
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    msg = ""
    if request.method == "POST":
        for key in ("morning_time", "evening_time"):
            val = request.form.get(key, "").strip()
            if (len(val) == 5 and val[2] == ":" and val[:2].isdigit() and val[3:].isdigit()
                    and 0 <= int(val[:2]) <= 23 and 0 <= int(val[3:]) <= 59):
                db().execute("UPDATE settings SET value=? WHERE key=?", (val, key))
        warn = request.form.get("warn_minutes", "").strip()
        if warn.isdigit():
            db().execute("UPDATE settings SET value=? WHERE key=?", (warn, "warn_minutes"))
        db().commit()
        msg = "Saved."
        return redirect(url_for("settings"))
    body = (
        f'<header><h1>Settings</h1><a class="link" href="/">Back</a></header>'
        f'<div class="date">Feeding times and warning window</div>'
        f'<form method="post"><div class="card" style="display:block">'
        f'<label>Morning feed time</label>'
        f'<input type="time" name="morning_time" value="{get_setting("morning_time")}">'
        f'<label>Evening feed time</label>'
        f'<input type="time" name="evening_time" value="{get_setting("evening_time")}">'
        f'<label>Warn this many minutes before (amber glow)</label>'
        f'<input type="number" name="warn_minutes" min="0" max="720" value="{get_setting("warn_minutes")}">'
        f'<div style="margin-top:16px"><button class="feed-btn" type="submit">Save</button></div>'
        f'</div></form>'
    )
    return PAGE.format(body=body)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000)
