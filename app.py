from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
from flask import Flask, Response, jsonify, render_template, request, session, redirect, url_for

import shiftoptim.config as config
from shiftoptim.ingest import build_schedule
from shiftoptim.render import render_html
from shiftoptim.models import Resident, Schedule
from shiftoptim.optimizer import CycleResult

# Import database helpers
from shiftoptim.database import (
    init_db, reset_db_run, get_settings, update_settings,
    authenticate_user, change_password, save_initial_schedule,
    load_schedule_from_db, get_swap_counts, get_locked_shifts,
    get_rejected_trades, add_rejected_trade, propose_trades,
    get_all_trades_for_iteration, cast_vote, check_and_advance_iteration,
    get_original_assignment, get_full_trade_history_log
)

app = Flask(__name__)
app.secret_key = "shiftoptim-live-dev-secure-key"

PREFS_CSV = Path("data/preferences.csv")
ICS_DIR = Path("data/ics")

# Initialize database on startup
init_db()

@app.route("/")
def index():
    return render_template("live.html")

# --- Authentication APIs ---

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
        
    user = authenticate_user(username, password)
    if user:
        session["username"] = user["username"]
        session["display_name"] = user["display_name"]
        session["is_admin"] = bool(user["is_admin"])
        return jsonify({
            "ok": True,
            "user": {
                "username": user["username"],
                "display_name": user["display_name"],
                "is_admin": bool(user["is_admin"])
            }
        })
    else:
        return jsonify({"error": "Invalid username or password"}), 401

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/change-password", methods=["POST"])
def api_change_password():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json(force=True) or {}
    new_password = data.get("new_password", "").strip()
    
    if not new_password:
        return jsonify({"error": "New password required"}), 400
        
    if change_password(session["username"], new_password):
        return jsonify({"ok": True})
    else:
        return jsonify({"error": "Failed to update password"}), 500

@app.route("/api/residents", methods=["GET"])
def api_residents():
    # Helper to return a list of registered resident display names (for the dropdown)
    import sqlite3
    from shiftoptim.database import get_db_connection
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT username, display_name FROM users WHERE is_admin = 0 ORDER BY display_name ASC").fetchall()
        return jsonify({"residents": [dict(r) for r in rows]})
    finally:
        conn.close()

# --- Dashboard State API ---

@app.route("/api/dashboard-state", methods=["GET"])
def api_dashboard_state():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    settings = get_settings()
    if not settings:
        return jsonify({"error": "Settings not initialized"}), 500
        
    username = session["username"]
    is_admin = session["is_admin"]
    
    state = {
        "status": settings["status"],
        "current_iteration": settings["current_iteration"],
        "max_iterations": settings["max_iterations"],
        "max_swaps": settings["max_swaps"],
        "n_max": settings["n_max"],
        "allow_jeopardy": bool(settings["allow_jeopardy"]),
        "user": {
            "username": username,
            "display_name": session["display_name"],
            "is_admin": is_admin
        }
    }
    
    # Load trade history/log
    history = []
    for r in get_full_trade_history_log():
        history.append({
            "iteration": r["iteration"],
            "trade_data": r["trade_data"]
        })
    state["history_log"] = history
    
    if is_admin:
        # Admin gets everything for the current iteration
        state["all_trades"] = get_all_trades_for_iteration(settings["current_iteration"])
        state["swap_counts"] = dict(get_swap_counts())
        state["locked_count"] = len(get_locked_shifts())
        state["rejected_count"] = len(get_rejected_trades())
    else:
        # Resident gets only trades involving them in the current iteration
        all_iter_trades = get_all_trades_for_iteration(settings["current_iteration"])
        user_trades = []
        for t in all_iter_trades:
            involved_residents = set(move[0] for move in t["trade_data"]["moves"])
            if username in involved_residents:
                # Add user's specific vote status
                user_trades.append({
                    "id": t["id"],
                    "total_delta": t["total_delta"],
                    "trade_data": t["trade_data"],
                    "status": t["status"],
                    "my_vote": t["votes"].get(username, "pending"),
                    "votes": t["votes"] # to show other people's voting status
                })
        state["user_trades"] = user_trades
        
    return jsonify(state)

# --- Voting API ---

@app.route("/api/vote", methods=["POST"])
def api_vote():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.get_json(force=True) or {}
    trade_id = data.get("trade_id")
    decision = data.get("decision")
    
    if trade_id is None or not decision:
        return jsonify({"error": "trade_id and decision required"}), 400
        
    res = cast_vote(trade_id, session["username"], decision)
    if not res["ok"]:
        return jsonify(res), 400
        
    # Check if this completed the iteration, and advance if so
    check_and_advance_iteration()
    
    return jsonify({"ok": True})

# --- Admin Operations APIs ---

@app.route("/api/admin/initialize", methods=["POST"])
def api_admin_initialize():
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 401
        
    # Check if a preferences file was uploaded
    if "preferences" in request.files:
        file = request.files["preferences"]
        if file.filename != "":
            PREFS_CSV.parent.mkdir(parents=True, exist_ok=True)
            file.save(PREFS_CSV)
            
    # Get parameters
    max_swaps = int(request.form.get("maxSwaps", -1))
    n_max = int(request.form.get("nMax", 2))
    allow_jeopardy = 1 if request.form.get("allowJeopardy") == "true" else 0
    max_iterations = int(request.form.get("maxIterations", 20))
    
    try:
        # Reset DB run (retains admin credentials but clears schedules, settings, and other users)
        reset_db_run()
        
        # Save settings (status is 'running', current_iteration is 0 to bootstrap)
        update_settings(
            max_swaps=max_swaps,
            n_max=n_max,
            allow_jeopardy=allow_jeopardy,
            max_iterations=max_iterations,
            status="running",
            current_iteration=0
        )
        
        # Build schedule and download calendars (this downloads ICS files to data/ics)
        if allow_jeopardy:
            config.ALLOW_JEOPARDY_SWAPS = True
        else:
            config.ALLOW_JEOPARDY_SWAPS = False
            
        sched = build_schedule(ICS_DIR, PREFS_CSV)
        save_initial_schedule(sched)
        
        # Call check_and_advance_iteration() to bootstrap the first iteration (0 -> 1)
        check_and_advance_iteration()
        
        return jsonify({"ok": True})
        
    except Exception as exc:
        import traceback
        return jsonify({
            "error": str(exc),
            "trace": traceback.format_exc()
        }), 500

@app.route("/api/admin/stop", methods=["POST"])
def api_admin_stop():
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 401
        
    update_settings(
        max_swaps=-1,
        n_max=2,
        allow_jeopardy=0,
        max_iterations=20,
        status="idle",
        current_iteration=0
    )
    return jsonify({"ok": True})

# --- Report API ---

@app.route("/api/report")
def api_report():
    # Open report to any logged-in user (admin or resident)
    if "username" not in session:
        return redirect(url_for("index"))
        
    sched = load_schedule_from_db()
    original_assignment = get_original_assignment()
    
    # Load and deserialize the trade log
    log = []
    for r in get_full_trade_history_log():
        td = r["trade_data"]
        moves = [tuple(m) for m in td["moves"]]
        log.append(CycleResult(
            cycle=td["cycle"],
            deltas=td["deltas"],
            total_delta=td["total_delta"],
            moves=moves
        ))
        
    return render_html(sched, log, original_assignment)

if __name__ == "__main__":
    app.run(debug=True, threaded=True)
