import pytest
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, date

import shiftoptim.config as config
from shiftoptim.models import Resident, Schedule, Shift
from shiftoptim.ingest import build_schedule
from shiftoptim.database import (
    DB_PATH, init_db, reset_db_run, get_settings, update_settings,
    authenticate_user, change_password, save_initial_schedule,
    load_schedule_from_db, get_swap_counts, get_locked_shifts,
    get_rejected_trades, propose_trades, get_all_trades_for_iteration,
    cast_vote, check_and_advance_iteration
)

@pytest.fixture(autouse=True)
def setup_db():
    # Make sure DB is initialized and reset before each test
    init_db()
    reset_db_run()
    yield
    # Clean up after tests if desired

def test_db_init_and_reset():
    settings = get_settings()
    assert settings is not None
    assert settings["status"] == "idle"
    assert settings["current_iteration"] == 0
    
    # Check default admin user is seeded
    admin = authenticate_user("admin", "admin")
    assert admin is not None
    assert admin["is_admin"] == 1
    assert admin["display_name"] == "Admin"

def test_user_authentication_and_passwords():
    # Attempt login with invalid user
    assert authenticate_user("nonexistent", "password") is None
    
    # Authenticate admin
    admin = authenticate_user("admin", "admin")
    assert admin is not None
    
    # Change password
    assert change_password("admin", "new-secure-password") is True
    assert authenticate_user("admin", "admin") is None
    assert authenticate_user("admin", "new-secure-password") is not None
    
    # Revert admin password for subsequent tests/usage
    assert change_password("admin", "admin") is True

def test_schedule_save_and_load():
    # Rebuild schedule using existing test files
    sched = build_schedule(Path("data/ics"), Path("data/preferences.csv"))
    
    # Save schedule state to SQLite
    save_initial_schedule(sched)
    
    # Verify resident accounts are created with default passwords
    for r_name in sched.residents:
        user = authenticate_user(r_name, r_name) # default password is the username
        assert user is not None
        assert user["is_admin"] == 0
        
    # Reload schedule from DB
    db_sched = load_schedule_from_db()
    
    assert len(db_sched.residents) == len(sched.residents)
    assert len(db_sched.shifts) == len(sched.shifts)
    
    # Verify shifts properties are identical
    for uid, original_shift in sched.shifts.items():
        db_shift = db_sched.shifts[uid]
        assert db_shift.uid == original_shift.uid
        assert db_shift.owner == original_shift.owner
        assert db_shift.loc == original_shift.loc
        assert db_shift.type == original_shift.type
        assert db_shift.work_date == original_shift.work_date
        assert db_shift.is_jeopardy == original_shift.is_jeopardy

def test_voting_and_iteration_transitions():
    sched = build_schedule(Path("data/ics"), Path("data/preferences.csv"))
    save_initial_schedule(sched)
    
    # Set status to running and current_iteration to 0 to bootstrap iteration 1
    update_settings(
        max_swaps=-1,
        n_max=2,
        allow_jeopardy=1,
        max_iterations=5,
        status="running",
        current_iteration=0
    )
    
    # Trigger first iteration proposal generation
    advanced = check_and_advance_iteration()
    assert advanced is True
    
    settings = get_settings()
    assert settings["current_iteration"] == 1
    assert settings["status"] in ("running", "done")
    
    if settings["status"] == "running":
        trades = get_all_trades_for_iteration(1)
        assert len(trades) > 0
        
        # Approve the first trade fully, and deny all other trades
        for idx, t in enumerate(trades):
            trade_id = t["id"]
            voters = list(t["votes"].keys())
            if idx == 0:
                for v in voters:
                    res = cast_vote(trade_id, v, "approve")
                    assert res["ok"] is True
            else:
                res = cast_vote(trade_id, voters[0], "deny")
                assert res["ok"] is True
            
        # Verify that check_and_advance_iteration now triggers a transition to Iteration 2
        # (or terminates if no more trades are found)
        advanced2 = check_and_advance_iteration()
        assert advanced2 is True
        
        # If advanced to iteration 2, verify settings
        new_settings = get_settings()
        if new_settings["status"] == "running":
            assert new_settings["current_iteration"] == 2
        else:
            assert new_settings["status"] == "done"
            
        # Verify rejected trades table populated
        if len(trades) > 1:
            rejected = get_rejected_trades()
            assert len(rejected) > 0
