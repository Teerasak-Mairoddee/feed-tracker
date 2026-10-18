# Deploy: "Have the cats been fed?"

A shared page your housemates open on their phones to log the cat's morning and evening meals. Runs on the Orange Pi at **http://192.168.1.60:8000** on your home wifi.

## 1. Copy the app onto the board
From your PC, in the folder that has `app.py`:
```
scp app.py root@192.168.1.60:/opt/catfeeder/app.py
```
If the folder doesn't exist yet, first SSH in and make it:
```
ssh root@192.168.1.60
mkdir -p /opt/catfeeder
exit
```
(Or just paste the file in with `nano /opt/catfeeder/app.py` on the board.)

## 2. Edit the names
SSH in and open the file:
```
ssh root@192.168.1.60
nano /opt/catfeeder/app.py
```
At the top, change:
- `HOUSEMATES` — the people who feed the cat.
- `CATS` — your cat's name(s). One cat is fine; two makes a card per cat.

Ctrl+O, Enter, Ctrl+X to save.

## 3. Install Flask
```
sudo apt update && sudo apt install -y python3-flask
```

## 4. Test it
```
cd /opt/catfeeder
python3 app.py
```
On your phone, open **http://192.168.1.60:8000**. Tap a meal, pick your name, Mark fed. Working? Press Ctrl+C on the board to stop it, then make it permanent below.

## 5. Run it automatically on boot
```
sudo tee /etc/systemd/system/catfeeder.service >/dev/null <<'EOF'
[Unit]
Description=Cat feeder log
After=network-online.target static-ip.service

[Service]
WorkingDirectory=/opt/catfeeder
ExecStart=/usr/bin/python3 /opt/catfeeder/app.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now catfeeder.service
sudo systemctl status catfeeder.service
```
Now it's always on at **http://192.168.1.60:8000**, even after a reboot.

## Updating to a new version
If you've already got it running and I send you a new `app.py`, just replace it and restart:
```
scp app.py tee@192.168.1.60:/opt/catfeeder/app.py
ssh tee@192.168.1.60 'sudo systemctl restart catfeeder'
```
Your `feeds.db` and settings are kept.

## Settings and status light
- Open **Settings** (top-right link) to set the **morning** and **evening** feed times, and how many minutes before a feed the warning starts.
- Each meal shows a status dot:
  - **grey** — not due yet (shows the scheduled time)
  - **amber, glowing** — feeding time is approaching (within your warning window)
  - **red, glowing** — overdue, with how long past
  - **green** — fed, with who and when
- The page refreshes itself every 60 seconds, so the dots update on their own. Good as an always-on tab.

## History grid
- A small GitHub-contributions-style grid sits in a card on the main page: 7 weekday rows x the last 26 weeks. **One tiny square per day**, coloured by that day's feeds combined (worst meal wins):
  - **green** on time (within 30 min of the set time)
  - **amber** late (within 2 hours)
  - **red** very late (over 2 hours)
  - **dark red** a meal was missed that day
  - faint grey, days before you started / future; solid grey, today not fed yet
- A small key sits under it. Tap or hover a square for that day's detail (time and who fed). Days before your first logged feed stay blank, not marked missed.
- To show more or fewer weeks, change `calendar_card(weeks=26)` in `app.py`. Thresholds are `LATE_GRACE_MIN` / `VERY_LATE_MIN` near the top. Restart after editing.

## Leaderboard
- A **Leaderboard** card on the main page ranks housemates by total feeds (all time), with a bar for each.
- A **streak** badge shows consecutive days a person has fed: a plain "N days" pill, which turns into a **HOT N** pill once they hit 3 days in a row (set by `HOT_STREAK_DAYS` near the top). The streak counts days ending today, or yesterday if today isn't fed yet, so it doesn't reset the moment you wake up.

## iPhone / narrow screens
- The history grid scrolls sideways and now **auto-scrolls to the newest week** on load, so the most recent days are visible without dragging. Older weeks are a swipe to the left.

## Tips
- **Bookmark it** on each phone's home screen so it feels like an app.
- The log resets each day automatically (it tracks by date) and keeps 7 days of history.
- Data lives in `/opt/catfeeder/feeds.db`. Back it up by copying that file.
- To change housemate or cat names: edit `app.py`, then `sudo systemctl restart catfeeder`. (Feed times are in Settings, no restart needed.)

## How it works
A single Python file using Flask (web) and SQLite (storage, built into Python). One row per cat/meal/day, so a meal can't be double-logged. "Undo" removes today's entry if someone taps by mistake. Settings live in the database. No accounts — anyone who can reach it can log a feed, which is the point.
