import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime, date
from collections import Counter
from werkzeug.security import generate_password_hash, check_password_hash

from .models import Schedule, Shift, Resident
from .config import LOCAL_TZ

DB_PATH = Path("data/live_mode.db")

def get_db_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    try:
        with conn:
            # 1. Settings Table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                max_swaps INTEGER NOT NULL,
                n_max INTEGER NOT NULL,
                allow_jeopardy INTEGER NOT NULL,
                max_iterations INTEGER NOT NULL,
                current_iteration INTEGER NOT NULL,
                status TEXT NOT NULL
            )
            """)

            # 2. Users Table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL
            )
            """)

            # 3. Residents Table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS residents (
                name TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                loc_pref TEXT NOT NULL,
                loc_weight REAL NOT NULL,
                type_pref TEXT NOT NULL,
                type_weight REAL NOT NULL,
                days_pref INTEGER NOT NULL,
                days_weight REAL NOT NULL,
                days_off TEXT NOT NULL
            )
            """)

            # 4. Shifts Table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS shifts (
                uid TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                original_owner TEXT NOT NULL,
                summary TEXT NOT NULL,
                t_start TEXT NOT NULL,
                t_end TEXT NOT NULL,
                loc TEXT,
                type TEXT,
                work_date TEXT NOT NULL,
                is_jeopardy INTEGER NOT NULL
            )
            """)

            # 5. Locked Shifts
            conn.execute("""
            CREATE TABLE IF NOT EXISTS locked_shifts (
                shift_uid TEXT PRIMARY KEY
            )
            """)

            # 6. Swap Counts
            conn.execute("""
            CREATE TABLE IF NOT EXISTS swap_counts (
                resident_name TEXT PRIMARY KEY,
                count INTEGER NOT NULL
            )
            """)

            # 7. Rejected Trades
            conn.execute("""
            CREATE TABLE IF NOT EXISTS rejected_trades (
                trade_key TEXT PRIMARY KEY
            )
            """)

            # 8. Proposed Trades
            conn.execute("""
            CREATE TABLE IF NOT EXISTS proposed_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration INTEGER NOT NULL,
                total_delta REAL NOT NULL,
                trade_data TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """)

            # 9. Trade Votes
            conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_votes (
                trade_id INTEGER NOT NULL,
                resident_name TEXT NOT NULL,
                vote TEXT NOT NULL,
                PRIMARY KEY (trade_id, resident_name),
                FOREIGN KEY (trade_id) REFERENCES proposed_trades(id) ON DELETE CASCADE
            )
            """)

            # 10. Trade Log
            conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration INTEGER NOT NULL,
                trade_data TEXT NOT NULL
            )
            """)

            # Seed admin user if not exists
            row = conn.execute("SELECT 1 FROM users WHERE username = 'admin'").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO users (username, display_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
                    ("admin", "Admin", generate_password_hash("admin"), 1)
                )

            # Insert default settings if not exists
            row_settings = conn.execute("SELECT 1 FROM settings WHERE id = 1").fetchone()
            if not row_settings:
                conn.execute(
                    "INSERT INTO settings (id, max_swaps, n_max, allow_jeopardy, max_iterations, current_iteration, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (1, -1, 2, 0, 20, 0, "idle")
                )
    finally:
        conn.close()

def reset_db_run():
    """Resets all simulation-specific tables, retaining admin credentials but clearing everything else."""
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM settings")
            conn.execute("DELETE FROM residents")
            conn.execute("DELETE FROM shifts")
            conn.execute("DELETE FROM locked_shifts")
            conn.execute("DELETE FROM swap_counts")
            conn.execute("DELETE FROM rejected_trades")
            conn.execute("DELETE FROM proposed_trades")
            conn.execute("DELETE FROM trade_votes")
            conn.execute("DELETE FROM trade_log")
            conn.execute("DELETE FROM users WHERE is_admin = 0")

            # Restore default settings
            conn.execute(
                "INSERT INTO settings (id, max_swaps, n_max, allow_jeopardy, max_iterations, current_iteration, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1, -1, 2, 0, 20, 0, "idle")
            )
    finally:
        conn.close()

# --- Settings ---
def get_settings():
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def update_settings(max_swaps, n_max, allow_jeopardy, max_iterations, status=None, current_iteration=None):
    conn = get_db_connection()
    try:
        with conn:
            if status is not None and current_iteration is not None:
                conn.execute(
                    "UPDATE settings SET max_swaps=?, n_max=?, allow_jeopardy=?, max_iterations=?, status=?, current_iteration=? WHERE id=1",
                    (max_swaps, n_max, allow_jeopardy, max_iterations, status, current_iteration)
                )
            elif status is not None:
                conn.execute(
                    "UPDATE settings SET max_swaps=?, n_max=?, allow_jeopardy=?, max_iterations=?, status=? WHERE id=1",
                    (max_swaps, n_max, allow_jeopardy, max_iterations, status)
                )
            else:
                conn.execute(
                    "UPDATE settings SET max_swaps=?, n_max=?, allow_jeopardy=?, max_iterations=? WHERE id=1",
                    (max_swaps, n_max, allow_jeopardy, max_iterations)
                )
    finally:
        conn.close()

# --- Users ---
def authenticate_user(username, password):
    username = username.strip().lower()
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            return dict(row)
        return None
    finally:
        conn.close()

def create_or_update_resident_user(name, display_name, conn=None):
    username = name.strip().lower()
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        if should_close:
            with conn:
                row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
                if not row:
                    # Default password is the username
                    conn.execute(
                        "INSERT INTO users (username, display_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
                        (username, display_name, generate_password_hash(username), 0)
                    )
        else:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                # Default password is the username
                conn.execute(
                    "INSERT INTO users (username, display_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
                    (username, display_name, generate_password_hash(username), 0)
                )
    finally:
        if should_close:
            conn.close()

def change_password(username, new_password):
    username = username.strip().lower()
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (generate_password_hash(new_password), username)
            )
            return True
    except Exception:
        return False
    finally:
        conn.close()

# --- Schedule Loading/Saving ---
def save_initial_schedule(sched: Schedule):
    conn = get_db_connection()
    try:
        with conn:
            # Save residents
            for r in sched.residents.values():
                days_off_str = json.dumps([d.isoformat() for d in r.days_off])
                conn.execute(
                    "INSERT OR REPLACE INTO residents (name, display_name, loc_pref, loc_weight, type_pref, type_weight, days_pref, days_weight, days_off) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (r.name, r.name.title(), r.loc_pref, r.loc_weight, r.type_pref, r.type_weight, r.days_pref, r.days_weight, days_off_str)
                )
                create_or_update_resident_user(r.name, r.name.title(), conn)

            # Save shifts
            for s in sched.shifts.values():
                conn.execute(
                    "INSERT OR REPLACE INTO shifts (uid, owner, original_owner, summary, t_start, t_end, loc, type, work_date, is_jeopardy) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (s.uid, s.owner, s.owner, s.summary, s.t_start.isoformat(), s.t_end.isoformat(), s.loc, s.type, s.work_date.isoformat(), 1 if s.is_jeopardy else 0)
                )

            # Initialize swap counts to 0
            for name in sched.residents:
                conn.execute("INSERT OR IGNORE INTO swap_counts (resident_name, count) VALUES (?, 0)", (name,))
    finally:
        conn.close()

def load_schedule_from_db() -> Schedule:
    import dateutil.tz
    from .ingest import LOCAL
    
    conn = get_db_connection()
    try:
        # Load Residents
        residents = {}
        for row in conn.execute("SELECT * FROM residents").fetchall():
            days_off = frozenset(date.fromisoformat(d) for d in json.loads(row["days_off"]))
            residents[row["name"]] = Resident(
                name=row["name"],
                loc_pref=row["loc_pref"],
                loc_weight=row["loc_weight"],
                type_pref=row["type_pref"],
                type_weight=row["type_weight"],
                days_pref=row["days_pref"],
                days_weight=row["days_weight"],
                days_off=days_off
            )

        # Load Shifts
        shifts = {}
        assignment = {name: set() for name in residents}
        for row in conn.execute("SELECT * FROM shifts").fetchall():
            # Parse timestamps with LOCAL timezone
            t_start = datetime.fromisoformat(row["t_start"]).astimezone(LOCAL) if "+" in row["t_start"] else datetime.fromisoformat(row["t_start"]).replace(tzinfo=LOCAL)
            t_end = datetime.fromisoformat(row["t_end"]).astimezone(LOCAL) if "+" in row["t_end"] else datetime.fromisoformat(row["t_end"]).replace(tzinfo=LOCAL)
            work_date = date.fromisoformat(row["work_date"])
            
            s = Shift(
                uid=row["uid"],
                owner=row["owner"],
                t_start=t_start,
                t_end=t_end,
                loc=row["loc"],
                type=row["type"],
                work_date=work_date,
                summary=row["summary"],
                is_jeopardy=bool(row["is_jeopardy"])
            )
            shifts[s.uid] = s
            assignment.setdefault(s.owner, set()).add(s.uid)

        # Ensure any owners not in residents are handled (fallback)
        for owner in assignment:
            if owner not in residents:
                residents[owner] = Resident(owner, "ANY", 0, "ANY", 0, 4, 0, frozenset())

        # Compute original hours from original_owner in DB
        orig_hours_by_resident = {}
        for row in conn.execute("SELECT original_owner, t_start, t_end FROM shifts").fetchall():
            orig_owner = row["original_owner"]
            t_start = datetime.fromisoformat(row["t_start"])
            t_end = datetime.fromisoformat(row["t_end"])
            duration = (t_end - t_start).total_seconds() / 3600.0
            orig_hours_by_resident[orig_owner] = orig_hours_by_resident.get(orig_owner, 0.0) + duration

        for r in residents.values():
            r.orig_hours = orig_hours_by_resident.get(r.name, 0.0)

        return Schedule(assignment=assignment, shifts=shifts, residents=residents)
    finally:
        conn.close()

# --- State Helpers ---
def get_swap_counts() -> Counter:
    conn = get_db_connection()
    try:
        counts = Counter()
        for row in conn.execute("SELECT * FROM swap_counts").fetchall():
            counts[row["resident_name"]] = row["count"]
        return counts
    finally:
        conn.close()

def get_locked_shifts() -> set[str]:
    conn = get_db_connection()
    try:
        locked = set()
        for row in conn.execute("SELECT * FROM locked_shifts").fetchall():
            locked.add(row["shift_uid"])
        return locked
    finally:
        conn.close()

def get_rejected_trades() -> set[frozenset]:
    conn = get_db_connection()
    try:
        rejected = set()
        for row in conn.execute("SELECT * FROM rejected_trades").fetchall():
            moves = [tuple(m) for m in json.loads(row["trade_key"])]
            rejected.add(frozenset(moves))
        return rejected
    finally:
        conn.close()

def add_rejected_trade(trade_key: frozenset[tuple[str, str, str]]):
    from .optimizer import swap_key
    sorted_moves = sorted(list(trade_key))
    key_str = json.dumps(sorted_moves)
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("INSERT OR IGNORE INTO rejected_trades (trade_key) VALUES (?)", (key_str,))
    finally:
        conn.close()

# --- Proposed Trades and Voting ---
def serialize_swap_key(key: frozenset[tuple[str, str, str]]) -> str:
    return json.dumps(sorted(list(key)))

def _fmt_time(dt) -> str:
    h = dt.hour
    m = dt.minute
    suffix = "p" if h >= 12 else "a"
    h_12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
    if m == 0:
        return f"{h_12}{suffix}"
    return f"{h_12}:{m:02d}{suffix}"

def serialize_trade(result, sched) -> dict:
    moves = []
    for giver, u, v in result.moves:
        su, sv = sched.shifts[u], sched.shifts[v]
        moves.append({
            "giver": giver,
            "giveUid": u,
            "giveSummary": su.summary,
            "giveDate": su.work_date.isoformat(),
            "giveLoc": su.loc,
            "giveType": su.type,
            "giveStart": _fmt_time(su.t_start),
            "giveEnd": _fmt_time(su.t_end),
            "recvUid": v,
            "recvSummary": sv.summary,
            "recvDate": sv.work_date.isoformat(),
            "recvLoc": sv.loc,
            "recvType": sv.type,
            "recvStart": _fmt_time(sv.t_start),
            "recvEnd": _fmt_time(sv.t_end),
            "delta": round(result.deltas.get(giver, 0), 4),
        })
    return {
        "cycle": result.cycle,
        "deltas": result.deltas,
        "total_delta": round(result.total_delta, 4),
        "moves": moves
    }

def propose_trades(trades_list, sched, iteration: int):
    conn = get_db_connection()
    try:
        with conn:
            for cand in trades_list:
                trade_dict = serialize_trade(cand, sched)
                trade_data = json.dumps(trade_dict)
                cursor = conn.execute(
                    "INSERT INTO proposed_trades (iteration, total_delta, trade_data, status) VALUES (?, ?, ?, ?)",
                    (iteration, cand.total_delta, trade_data, "pending")
                )
                trade_id = cursor.lastrowid
                
                # Identify involved residents (all givers in moves)
                involved = set(giver for giver, _, _ in cand.moves)
                for res_name in involved:
                    conn.execute(
                        "INSERT INTO trade_votes (trade_id, resident_name, vote) VALUES (?, ?, ?)",
                        (trade_id, res_name, "pending")
                    )
    finally:
        conn.close()

def get_all_trades_for_iteration(iteration: int):
    conn = get_db_connection()
    try:
        trades = []
        rows = conn.execute("SELECT * FROM proposed_trades WHERE iteration = ?", (iteration,)).fetchall()
        for r in rows:
            trade_id = r["id"]
            votes_rows = conn.execute("SELECT resident_name, vote FROM trade_votes WHERE trade_id = ?", (trade_id,)).fetchall()
            votes = {vr["resident_name"]: vr["vote"] for vr in votes_rows}
            trades.append({
                "id": trade_id,
                "iteration": r["iteration"],
                "total_delta": r["total_delta"],
                "trade_data": json.loads(r["trade_data"]),
                "status": r["status"],
                "votes": votes
            })
        return trades
    finally:
        conn.close()

def cast_vote(trade_id: int, username: str, decision: str) -> dict:
    """Cast a resident's vote. Handles auto-transition of trade status to approved/rejected."""
    username = username.strip().lower()
    if decision not in ("approve", "deny"):
        return {"ok": False, "error": "Invalid decision"}

    conn = get_db_connection()
    try:
        with conn:
            # Update the vote
            conn.execute(
                "UPDATE trade_votes SET vote = ? WHERE trade_id = ? AND resident_name = ?",
                (decision, trade_id, username)
            )

            # Check trade status
            trade = conn.execute("SELECT * FROM proposed_trades WHERE id = ?", (trade_id,)).fetchone()
            if not trade:
                return {"ok": False, "error": "Trade not found"}

            all_votes = conn.execute("SELECT * FROM trade_votes WHERE trade_id = ?", (trade_id,)).fetchall()
            
            # If any participant denies, the entire trade is immediately rejected
            if any(v["vote"] == "deny" for v in all_votes):
                conn.execute("UPDATE proposed_trades SET status = 'rejected' WHERE id = ?", (trade_id,))
                
                # Add to rejected_trades key list so it is never proposed again
                trade_dict = json.loads(trade["trade_data"])
                moves = [tuple(m) for m in trade_dict["moves"]]
                key_str = json.dumps(sorted(moves))
                conn.execute("INSERT OR IGNORE INTO rejected_trades (trade_key) VALUES (?)", (key_str,))
                
            # If all participants approve, the trade is approved
            elif all(v["vote"] == "approve" for v in all_votes):
                conn.execute("UPDATE proposed_trades SET status = 'approved' WHERE id = ?", (trade_id,))

        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()

def check_and_advance_iteration() -> bool:
    """Check if all proposed trades in the current iteration are resolved.
    If they are, applies approved ones and generates proposals for the next iteration.
    Returns True if advanced, False otherwise.
    """
    settings = get_settings()
    if not settings or settings["status"] != "running":
        return False

    iter_idx = settings["current_iteration"]
    
    conn = get_db_connection()
    try:
        # Check if there are any pending trades left for this iteration
        pending = conn.execute(
            "SELECT count(*) as c FROM proposed_trades WHERE iteration = ? AND status = 'pending'",
            (iter_idx,)
        ).fetchone()["c"]
        
        if pending > 0:
            return False  # Still waiting on votes

        # All trades are resolved! Start transaction to apply approvals & calculate next iteration.
        with conn:
            # 1. Fetch approved trades for this iteration
            approved_rows = conn.execute(
                "SELECT * FROM proposed_trades WHERE iteration = ? AND status = 'approved'",
                (iter_idx,)
            ).fetchall()
            
            # Load schedule to apply approved trades to database
            # We will perform this in-memory and then write back the updated schedule
            sched = load_schedule_from_db()
            
            for row in approved_rows:
                trade_id = row["id"]
                trade_dict = json.loads(row["trade_data"])
                
                # Reconstruct CycleResult
                from .optimizer import CycleResult, apply_cycle
                moves = [(m["giver"], m["giveUid"], m["recvUid"]) for m in trade_dict["moves"]]
                cand = CycleResult(
                    cycle=trade_dict["cycle"],
                    deltas=trade_dict["deltas"],
                    total_delta=trade_dict["total_delta"],
                    moves=moves
                )
                
                # Apply changes to the in-memory schedule object
                apply_cycle(cand, sched)
                
                # Record to trade_log
                conn.execute(
                    "INSERT INTO trade_log (iteration, trade_data) VALUES (?, ?)",
                    (iter_idx, row["trade_data"])
                )

                # Lock the shifts involved
                for _, u, v in cand.moves:
                    conn.execute("INSERT OR REPLACE INTO locked_shifts (shift_uid) VALUES (?)", (u,))
                    conn.execute("INSERT OR REPLACE INTO locked_shifts (shift_uid) VALUES (?)", (v,))
                
                # Increment beneficiary swap counts
                beneficiary = max(sorted(cand.deltas.keys()), key=lambda n: cand.deltas[n])
                conn.execute(
                    "INSERT INTO swap_counts (resident_name, count) VALUES (?, 1) ON CONFLICT(resident_name) DO UPDATE SET count = count + 1",
                    (beneficiary,)
                )

            # Save the updated shifts state back to the database
            for uid, s in sched.shifts.items():
                conn.execute(
                    "UPDATE shifts SET owner = ? WHERE uid = ?",
                    (s.owner, uid)
                )

            # 2. Re-evaluate / generate next iteration trades
            next_iter = iter_idx + 1
            
            # Check max iterations limit
            if next_iter > settings["max_iterations"]:
                conn.execute("UPDATE settings SET status = 'done' WHERE id = 1")
                return True

            # Re-generate candidates using the updated state
            from .graph import build_trade_graph, find_cycles
            from .optimizer import evaluate_cycle, _can_add, swap_key
            
            locked = set(r["shift_uid"] for r in conn.execute("SELECT shift_uid FROM locked_shifts").fetchall())
            swap_count = Counter()
            for r in conn.execute("SELECT resident_name, count FROM swap_counts").fetchall():
                swap_count[r["resident_name"]] = r["count"]
            rejected = set()
            for r in conn.execute("SELECT trade_key FROM rejected_trades").fetchall():
                moves = [tuple(m) for m in json.loads(r["trade_key"])]
                rejected.add(frozenset(moves))

            # Build trade graph
            G = build_trade_graph(sched, locked)
            
            candidates = []
            for cyc in find_cycles(G, settings["n_max"]):
                res = evaluate_cycle(cyc, sched)
                if res is None:
                    continue
                if swap_key(res) in rejected:
                    continue
                if settings["max_swaps"] != -1:
                    beneficiary = max(sorted(res.deltas.keys()), key=lambda n: res.deltas[n])
                    if swap_count[beneficiary] + 1 > settings["max_swaps"]:
                        continue
                candidates.append(res)
            
            # Select independent trades
            candidates.sort(key=lambda r: r.total_delta, reverse=True)
            
            # Build original assignment mappings for _can_add checks
            # Note: _can_add checks feasibility against the original schedule snapshot.
            # In our db, original owners are stored in original_owner field in shifts.
            # Let's rebuild the original schedule to perform independence verification.
            orig_assignment = {name: set() for name in sched.residents}
            for row in conn.execute("SELECT uid, original_owner FROM shifts").fetchall():
                orig_assignment[row["original_owner"]].add(row["uid"])
            
            from .utility import utility
            orig_util = {}
            for name in sched.residents:
                orig_shifts = [sched.shifts[uid] for uid in orig_assignment[name]]
                orig_util[name] = utility(orig_shifts, sched.residents[name])

            used_shifts = set()
            participation = {}
            res_trades = {}
            selected = []

            for cand in candidates:
                cand_shifts = {u for _, u, v in cand.moves} | {v for _, u, v in cand.moves}
                if cand_shifts & used_shifts:
                    continue
                if settings["max_swaps"] != -1:
                    if any(participation.get(name, 0) + swap_count.get(name, 0) + 1 > settings["max_swaps"]
                           for name in cand.deltas):
                        continue
                
                # Run independence checks relative to original schedule
                if not _can_add(cand, sched, orig_assignment, orig_util, res_trades):
                    continue

                # Accept the candidate for this iteration
                selected.append(cand)
                used_shifts |= cand_shifts
                for name in cand.deltas:
                    participation[name] = participation.get(name, 0) + 1
                    res_trades.setdefault(name, []).append(cand)

            if selected:
                # Insert the new proposed trades
                for cand in selected:
                    trade_dict = serialize_trade(cand, sched)
                    trade_data = json.dumps(trade_dict)
                    cursor = conn.execute(
                        "INSERT INTO proposed_trades (iteration, total_delta, trade_data, status) VALUES (?, ?, ?, ?)",
                        (next_iter, cand.total_delta, trade_data, "pending")
                    )
                    trade_id = cursor.lastrowid
                    
                    involved = set(giver for giver, _, _ in cand.moves)
                    for res_name in involved:
                        conn.execute(
                            "INSERT INTO trade_votes (trade_id, resident_name, vote) VALUES (?, ?, ?)",
                            (trade_id, res_name, "pending")
                        )
                
                # Advance current_iteration
                conn.execute(
                    "UPDATE settings SET current_iteration = ? WHERE id = 1",
                    (next_iter,)
                )
            else:
                # No more candidates, terminate
                conn.execute("UPDATE settings SET status = 'done' WHERE id = 1")

        return True
    except Exception as e:
        import traceback
        print(f"Error in check_and_advance_iteration: {e}")
        print(traceback.format_exc())
        return False
    finally:
        conn.close()

def get_original_assignment():
    conn = get_db_connection()
    try:
        orig = {}
        for row in conn.execute("SELECT uid, original_owner FROM shifts").fetchall():
            orig.setdefault(row["original_owner"], set()).add(row["uid"])
        return orig
    finally:
        conn.close()

def get_full_trade_history_log():
    conn = get_db_connection()
    try:
        history = []
        rows = conn.execute("SELECT * FROM trade_log ORDER BY id ASC").fetchall()
        for r in rows:
            history.append({
                "id": r["id"],
                "iteration": r["iteration"],
                "trade_data": json.loads(r["trade_data"])
            })
        return history
    finally:
        conn.close()
