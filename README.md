# ShiftMaxxer: Resident Shift Scheduling Exchange

ShiftMaxxer is a tool designed to discover mutually beneficial shift trades among emergency medicine residents. Rather than rebuilding a schedule from scratch, this tool takes an existing schedule and identifies voluntary swaps that increase resident satisfaction without violating hard constraints.

## How the Algorithm Works

The exchange mechanism operates through a directed trade graph where each shift is a node.

1. **Graph Construction.** The algorithm draws an edge from shift A to shift B if the owner of shift A is willing and able to trade for shift B. An edge exists only if the swap maintains schedule legality, respects the owner's day-off requests, and does not decrease their satisfaction. Beyond location, time-of-day, and streak preferences, swaps that hand a resident more total hours than they started with are penalized, so count-neutral trades cannot silently increase someone's workload hours.
2. **Cycle Search.** The algorithm searches for cycles in the graph up to a maximum length (typically 2 or 3). A 2-cycle represents a direct swap between two residents. A 3-cycle represents a three-way rotation.
3. **Greedy Execution.** The algorithm identifies all valid cycles that are strictly Pareto-improving, meaning at least one resident is happier and no resident is worse off. It executes the trade with the highest utility gain first, updates the schedule, and rebuilds the trade graph.
4. **Termination.** This process repeats until no further Pareto-improving trades can be found, or until participants reach their individual swap budgets.

ShiftMaxxer supports two execution modes that differ in how trades are selected and applied:

### Batch Mode (default)

The optimizer builds the trade graph once against a fixed snapshot of the original schedule, enumerates all valid Pareto-improving cycles, and selects a shift-disjoint set using a greedy pass with an all-subset independence check. Any subset of the selected trades can be applied in any order and is guaranteed to be ACGME-legal and utility-non-worsening for all participants. All selected trades are applied automatically without user intervention.

### Live Mode (`--live`)

The optimizer runs iteratively: it rebuilds the trade graph from the current schedule at each step, picks the single highest-gain Pareto-improving cycle, and pauses to display it on the command line and ask for confirmation before applying it. This allows a chief resident or coordinator to review each proposed swap individually and approve or reject it in real time.

- **Rejection memory.** Any swap that is denied is recorded by its exact move set and is never proposed again in the same session, so the next-best candidate surfaces on the following iteration.
- **Termination.** The session ends when all remaining candidates have been either blacklisted through rejection or exhausted by per-person participation caps.
- **Output.** After the interactive session concludes, the accepted-swap log is printed to the terminal and the HTML report is written, reflecting only the approved trades.

### Web Live-Voting Mode (`app.py`)

A browser-based alternative to CLI live mode. The Flask app (`app.py`) serves a dashboard where each resident logs in and votes to accept or reject proposed swaps. An admin initializes the session, sets optimizer parameters, and monitors progress. The app persists schedule state and votes in a local SQLite database via `shiftmaxxer/database.py`, so the session survives server restarts.

```bash
python app.py
```

Open `http://localhost:5000` in a browser. Residents cast votes; the optimizer advances to the next iteration once all participants in a trade have voted.

## Guarantees

The mechanism provides three core guarantees:

- **Schedule Legality.** Every proposed trade is checked against ACGME duty-hour rules (such as the 12-hour minimum rest period and the 6-day maximum consecutive work streak) and individual day-off requests. A trade that violates any rule is never executed.
- **Pareto Improvement.** A resident's utility is never decreased. Every trade makes at least one resident happier while leaving all other participants at least as satisfied as before.
- **Strict Workload Conservation.** Workloads are preserved. Residents only swap existing shifts, so everyone ends the process with the exact number of shifts they had at the start.

## Repository Structure

The project is structured as follows:

- [main.py](file:///Users/roshanlodha/Documents/shiftmaxxer/main.py): Command-line entrypoint for the batch and CLI live-mode optimizer.
- [app.py](file:///Users/roshanlodha/Documents/shiftmaxxer/app.py): Flask web application for browser-based live voting mode.
- [requirements.txt](file:///Users/roshanlodha/Documents/shiftmaxxer/requirements.txt): Python dependencies.
- [shiftmaxxer/](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer): The core Python package containing scheduling logic.
  - [config.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/config.py): Configuration settings and defaults (including `START_DATE` and `TIME_DIFF_WEIGHT`).
  - [models.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/models.py): Data structures for shifts, schedules, and residents.
  - [ingest.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/ingest.py): Logic to parse ICS calendar files and preference CSVs.
  - [feasibility.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/feasibility.py): Verification of ACGME duty-hour compliance.
  - [utility.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/utility.py): Satisfaction score and adjusted utility calculation (including the hours-difference penalty).
  - [graph.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/graph.py): Construction of the directed trade graph.
  - [optimizer.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/optimizer.py): Cycle detection and trade execution — both the batch single-snapshot optimizer and the iterative Live mode solver.
  - [database.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/database.py): SQLite persistence layer for the web live-voting mode (schedule state, votes, trade history).
  - [report.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/report.py): Plain text formatting for execution logs and the CLI confirmation prompt used in Live mode.
  - [render.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/render.py): HTML report generator.
- [templates/](file:///Users/roshanlodha/Documents/shiftmaxxer/templates): Jinja2 HTML templates served by the Flask app.
- [data/](file:///Users/roshanlodha/Documents/shiftmaxxer/data): Input schedules and preferences.
  - `ics/`: Input calendar files in iCalendar format.
  - `preferences.csv`: Resident preferences (location, time, streak length, weights, and days off).
- [tests/](file:///Users/roshanlodha/Documents/shiftmaxxer/tests): Automated tests.

## Installation and Usage

To set up the environment and run the optimizer:

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the main script to process the default data and generate an HTML report:
   ```bash
   python main.py
   ```

3. Customize execution using command-line arguments:
   ```bash
   python main.py -K 2 -n 2 --html customized_report.html
   ```

4. Run in Live mode to review and confirm each proposed swap interactively:
   ```bash
   python main.py --live
   ```

    Key arguments:
    - `-K`, `--max-swaps-per-person`: The maximum number of swaps any single resident can be charged with as the primary beneficiary (default: unlimited). Use -1 for unlimited.
    - `-n`, `--max-cycle`: The maximum cycle length to search for (2 for 1-for-1 swaps, 3 to include three-way rotations).
    - `--allow-jeopardy-swaps`: Allow jeopardy or backup shifts to participate in trading.
    - `--live`: Enable Live mode. Each proposed swap is displayed on the command line and must be confirmed (`y`) or rejected (`N`) before the algorithm proceeds. Rejected swaps are permanently blacklisted for the session.
    - `--html`: Output path for the HTML report (default: `shiftswap.html`).

    Additional settings:
    - `START_DATE` (in `shiftmaxxer/config.py`): Scheduled shifts occurring before this date (e.g., June 29, 2026) are ignored and excluded from trading.
    - `TIME_DIFF_WEIGHT` (in `shiftmaxxer/config.py`): Linear penalty subtracted from a resident's utility for each net additional hour gained vs. their original schedule. Default `0.02`. Set to `0.0` to disable the penalty and treat all shift lengths as equal.
