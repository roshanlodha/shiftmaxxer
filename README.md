# ShiftMaxxer: Resident Shift Scheduling Exchange

ShiftMaxxer is a tool designed to discover mutually beneficial shift trades among emergency medicine residents. Rather than rebuilding a schedule from scratch, this tool takes an existing schedule and identifies voluntary swaps that increase resident satisfaction without violating hard constraints.

## How the Algorithm Works

The exchange mechanism operates through a directed trade graph where each shift is a node. 

1. **Graph Construction.** The algorithm draws an edge from shift A to shift B if the owner of shift A is willing and able to trade for shift B. An edge exists only if the swap maintains schedule legality, respects the owner's day-off requests, and does not decrease their satisfaction.
2. **Cycle Search.** The algorithm searches for cycles in the graph up to a maximum length (typically 2 or 3). A 2-cycle represents a direct swap between two residents. A 3-cycle represents a three-way rotation.
3. **Greedy Execution.** The algorithm identifies all valid cycles that are strictly Pareto-improving, meaning at least one resident is happier and no resident is worse off. It executes the trade with the highest utility gain first, updates the schedule, and rebuilds the trade graph.
4. **Termination.** This process repeats until no further Pareto-improving trades can be found, or until participants reach their individual swap budgets.

## Guarantees

The mechanism provides three core guarantees:

- **Schedule Legality.** Every proposed trade is checked against ACGME duty-hour rules (such as the 12-hour minimum rest period and the 6-day maximum consecutive work streak) and individual day-off requests. A trade that violates any rule is never executed.
- **Pareto Improvement.** A resident's utility is never decreased. Every trade makes at least one resident happier while leaving all other participants at least as satisfied as before.
- **Strict Workload Conservation.** Workloads are preserved. Residents only swap existing shifts, so everyone ends the process with the exact number of shifts they had at the start.

## Repository Structure

The project is structured as follows:

- [main.py](file:///Users/roshanlodha/Documents/shiftmaxxer/main.py): The command-line entrypoint to run the schedule optimizer.
- [requirements.txt](file:///Users/roshanlodha/Documents/shiftmaxxer/requirements.txt): Python dependencies.
- [shiftmaxxer/](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer): The core Python package containing scheduling logic.
  - [config.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/config.py): Configuration settings and defaults.
  - [models.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/models.py): Data structures for shifts, schedules, and residents.
  - [ingest.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/ingest.py): Logic to parse ICS calendar files and preference CSVs.
  - [feasibility.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/feasibility.py): Verification of ACGME duty-hour compliance.
  - [utility.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/utility.py): Utility functions calculating satisfaction scores.
  - [graph.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/graph.py): Construction of the directed trade graph.
  - [optimizer.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/optimizer.py): The cycle detection and greedy trade execution loop.
  - [report.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/report.py): Plain text formatting for execution logs.
  - [render.py](file:///Users/roshanlodha/Documents/shiftmaxxer/shiftmaxxer/render.py): HTML report generator.
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

   Key arguments:
   - `-K`, `--max-swaps-per-person`: The maximum number of swaps any single resident can participate in (default: 3).
   - `-n`, `--max-cycle`: The maximum cycle length to search for (2 for 1-for-1 swaps, 3 to include three-way rotations).
   - `--allow-jeopardy-swaps`: Allow jeopardy or backup shifts to participate in trading.
