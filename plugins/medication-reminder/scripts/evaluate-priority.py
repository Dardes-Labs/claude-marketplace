#!/usr/bin/env python3
"""
Priority evaluator for medication reminders.

Reads a TOML config describing each medication's priority and take-window,
then decides what to do for each one given the current wall-clock time.

Output contract (one line per medication that needs attention):
    ACTION|MESSAGE
where ACTION ∈ {"urgent", "remind", "skip", "silent"}.

`silent` / `skip` lines may be emitted or omitted — the caller ignores them.
Anything else is ignored by medication-check.sh.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

# Keyword → (earliest, latest). Matches the documented set in
# config/medications.example.toml — keep them in sync.
TAKE_WINDOWS: dict[str, tuple[time, time]] = {
    "morning":   (time(7, 0),  time(10, 0)),
    "noon":      (time(11, 0), time(13, 0)),
    "afternoon": (time(13, 0), time(17, 0)),
    "evening":   (time(17, 0), time(20, 0)),
    "night":     (time(20, 0), time(23, 0)),
    "anytime":   (time(0, 0),  time(23, 59)),
}

# An explicit HH:MM target gets a 2-hour soft tail so "aim for 13:00" means
# "somewhere between 13:00 and 15:00 is fine".
HHMM_TAIL = timedelta(hours=2)


@dataclass(frozen=True)
class Medication:
    name: str
    priority: str              # "crucial" | "important" | "optional"
    earliest: time             # start of the take-window (inclusive)
    latest: time               # end of the take-window (inclusive)
    deadline: time | None      # optional hard cut-off; past this → skip today
    note: str = ""             # free-form, shown in the notification


def parse_hhmm(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def resolve_take(value: str) -> tuple[time, time]:
    """Turn the user-facing `take` field into an (earliest, latest) window."""
    if value in TAKE_WINDOWS:
        return TAKE_WINDOWS[value]
    # Treat as HH:MM — aim-for time with a 2-hour soft tail, clamped to 23:59.
    target = parse_hhmm(value)
    end_dt = (datetime.combine(datetime.today(), target) + HHMM_TAIL).time()
    if end_dt < target:  # midnight wraparound
        end_dt = time(23, 59)
    return target, end_dt


def load_config(path: Path) -> list[Medication]:
    data = tomllib.loads(path.read_text())
    meds: list[Medication] = []
    for entry in data.get("medication", []):
        earliest, latest = resolve_take(entry.get("take", "anytime"))
        deadline_raw = entry.get("deadline")
        meds.append(
            Medication(
                name=entry["name"],
                priority=entry.get("priority", "optional"),
                earliest=earliest,
                latest=latest,
                deadline=parse_hhmm(deadline_raw) if deadline_raw else None,
                note=entry.get("note", ""),
            )
        )
    return meds


# ---------------------------------------------------------------------------
# TODO: USER CONTRIBUTION — implement `evaluate()` below.
#
# This is the heart of the plugin. Given a medication and the current time,
# decide what to do. Your ADHD-experience judgment shapes this directly.
#
# Schema recap (after the simplification pass):
#   med.priority  ∈ {"crucial", "important", "optional"}
#   med.latest  — hard cut-off (Optional[time]); past this ⇒ skip today
#   med.note      — text to show in the notification
#
# Taken-state note: this function is only consulted when the medication is
# considered NOT YET taken today. The fast-path flag + HealthKit check in
# medication-check.sh gate whether this runs at all — don't re-check it here.
# (See README → "How 'taken' state is tracked" for the full model.)
#
# Guiding defaults you might encode:
#   • med.latest is None (no hard cut-off):
#       crucial   → urgent  (nag every session until taken)
#       important → remind  (medium urgency, every session)
#       optional  → remind  (gentle, every session)
#   • now > med.latest (past hard cut-off):
#       skip, regardless of priority — user set the cut-off deliberately
#   • now ≤ med.latest:
#       crucial   → urgent
#       important → remind
#       optional  → remind
#
# Inputs:
#   med: Medication
#   now: datetime.time (wall-clock, no timezone)
#
# Output:
#   (action: str, message: str)
#   action ∈ {"urgent", "remind", "skip", "silent"}
#   message is shown in the macOS notification body; leave "" to use med.note.
# ---------------------------------------------------------------------------
def evaluate(med: Medication, now: time) -> tuple[str, str]:
    raise NotImplementedError(
        "Implement evaluate() in evaluate-priority.py — see the TODO block above."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--now", help="HH:MM override for testing", default=None)
    args = ap.parse_args()

    if not args.config.exists():
        return 0  # nothing to do, stay silent

    now = parse_hhmm(args.now) if args.now else datetime.now().time().replace(microsecond=0)
    meds = load_config(args.config)

    for med in meds:
        try:
            action, message = evaluate(med, now)
        except NotImplementedError as e:
            print(f"evaluate-priority: {e}", file=sys.stderr)
            return 2
        if action in ("urgent", "remind"):
            # Prefer the user's note, fall back to the medication name.
            body = message or med.note or med.name
            print(f"{action}|{body}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
