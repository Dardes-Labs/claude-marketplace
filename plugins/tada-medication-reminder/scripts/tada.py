#!/usr/bin/env python3
"""
TaDa — Mac companion for the per-dose medication state.json.

The TaDa iOS app reads your schedule from Apple Health and syncs a per-dose
state.json into iCloud Drive. This CLI is the Mac surface over that file:

    tada notify                       macOS notification for any dose still pending
                                      past its scheduled time today (SessionStart hook)
    tada status                       print today's doses and their status
    tada take <med> [--at HH:MM|prn]  mark a dose Taken
    tada skip <med> [--at HH:MM|prn]  mark a dose Skipped
    tada undo <med> [--at HH:MM|prn]  reset the med's most-recent log to pending

A medication can be named by its display name or its id. Writes set
source="plugin"; the iOS app mirrors them into Apple Health. The plugin never
touches HealthKit — state.json is the only surface. See the PRD
(Dardes-Labs/tada-ios -> .claude/prds/tada-medication-sync.md), FR-5..FR-7.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone

SCHEMA_MAJOR = "1"
ICON = {"taken": "✓", "skipped": "✗", "pending": "○"}


def state_path():
    folder = os.environ.get(
        "MEDICATION_ICLOUD_DIR",
        os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/TaDa Medication Tracker"),
    )
    return os.environ.get("MEDICATION_STATE_FILE", os.path.join(folder, "state.json"))


def today_str():
    return date.today().isoformat()


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_hm():
    now = datetime.now()
    return (now.hour, now.minute)


def parse_hm(value):
    """'08:00' -> (8, 0); None / malformed -> None."""
    try:
        hours, minutes = str(value).split(":")
        return (int(hours), int(minutes))
    except (ValueError, AttributeError):
        return None


class StateError(Exception):
    pass


def load_state(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    version = str(data.get("schema_version", ""))
    if version.split(".")[0] != SCHEMA_MAJOR:
        raise StateError("unsupported schema_version %r" % version)
    return data


def is_stale(data):
    """True when the file doesn't describe today (the FR-5 date guard)."""
    return data.get("date") != today_str()


def atomic_write(path, data):
    folder = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".state-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --- notify (SessionStart hook) --------------------------------------------

def overdue_pending(data):
    now = now_hm()
    out = []
    for med in data.get("medications", []):
        for dose in med.get("doses", []):
            if dose.get("status") != "pending":
                continue
            when = parse_hm(dose.get("scheduled_at"))
            if when is not None and when <= now:
                out.append((med, dose))
    return out


def macos_notify(title, body):
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = 'display notification "%s" with title "%s"' % (esc(body), esc(title))
    try:
        subprocess.run(["osascript", "-e", script], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def cmd_notify(_args):
    try:
        data = load_state(state_path())
    except (OSError, ValueError, StateError):
        return 0  # missing / malformed -> stay silent (non-intrusive)
    if is_stale(data):
        return 0  # date guard: stale file == no data for today, never "done"
    pending = overdue_pending(data)
    if not pending:
        return 0
    labels = ["%s %s" % (m.get("name", "?"), d.get("scheduled_at", "")) for m, d in pending]
    count = len(labels)
    body = ", ".join(labels[:4]) + ("" if count <= 4 else ", +%d more" % (count - 4))
    macos_notify("TaDa — %d dose%s pending" % (count, "" if count == 1 else "s"), body)
    return 0


# --- status ----------------------------------------------------------------

def cmd_status(_args):
    path = state_path()
    try:
        data = load_state(path)
    except FileNotFoundError:
        print("No state.json at %s" % path)
        print("Install the TaDa iOS app and enable iCloud Drive — it produces this file.")
        return 0
    except (OSError, ValueError, StateError) as exc:
        print("Cannot read state.json: %s" % exc)
        return 1
    if is_stale(data):
        # Date guard (FR-6): a non-today file is no-data-for-today — don't list
        # yesterday's doses as if they were today's.
        print("TaDa — %s   (stale: not today — the iOS app hasn't published today yet)"
              % data.get("date", "?"))
        return 0
    print("TaDa — %s" % data.get("date", "?"))
    now = now_hm()
    meds = data.get("medications", [])
    if not meds:
        print("  (no medications)")
    for med in meds:
        print("  %s" % med.get("name", "?"))
        for dose in med.get("doses", []):
            status = dose.get("status", "pending")
            sched = dose.get("scheduled_at") or "PRN"
            when = parse_hm(dose.get("scheduled_at"))
            due = "   ← due" if status == "pending" and when is not None and when <= now else ""
            print("    %s  %-5s  %s%s" % (ICON.get(status, "?"), sched, status, due))
    return 0


# --- take / skip / undo ----------------------------------------------------

def med_fields(med):
    """Lower-cased (name, id) — a medication is resolvable by either."""
    return (med.get("name", "").lower(), str(med.get("id", "")).lower())


def resolve_med(data, query):
    # Match by name or id; an exact hit on either beats a substring hit.
    needle = query.lower()
    meds = data.get("medications", [])
    exact = [m for m in meds if needle in med_fields(m)]
    return exact or [m for m in meds if any(needle in f for f in med_fields(m))]


def is_prn(dose):
    """A dose with no scheduled clock time (as-needed)."""
    return parse_hm(dose.get("scheduled_at")) is None


def dose_at(med, at):
    """`--at HH:MM` targets that scheduled dose; `--at prn` an as-needed dose."""
    if str(at).strip().lower() == "prn":
        return next((d for d in med.get("doses", []) if is_prn(d)), None)
    want = parse_hm(at)
    if want is None:
        return None
    for dose in med.get("doses", []):
        if parse_hm(dose.get("scheduled_at")) == want:
            return dose
    return None


def dose_sort_key(dose):
    # Scheduled doses sort by clock time and ahead of PRN (which has no time).
    when = parse_hm(dose.get("scheduled_at"))
    return (0, when) if when is not None else (1, (0, 0))


def earliest_pending(med):
    pend = [d for d in med.get("doses", []) if d.get("status") == "pending"]
    return min(pend, key=dose_sort_key) if pend else None


def last_logged(med):
    # Most recently logged dose; on equal logged_at (same-second writes) prefer
    # the later-scheduled dose so undo is deterministic.
    logged = [d for d in med.get("doses", []) if d.get("logged_at")]
    if not logged:
        return None
    return max(logged, key=lambda d: (d["logged_at"], parse_hm(d.get("scheduled_at")) or (0, 0)))


def find_dose(data, med_id, med_name, scheduled_at):
    """Re-locate a dose by the PRD key (medication id, scheduled_at) in a fresh read.

    Falls back to matching the medication by name when it has no id.
    """
    want = parse_hm(scheduled_at)
    for med in data.get("medications", []):
        if med_id is not None:
            if med.get("id") != med_id:
                continue
        elif med.get("name", "").lower() != (med_name or "").lower():
            continue
        for dose in med.get("doses", []):
            if parse_hm(dose.get("scheduled_at")) == want:
                return med, dose
    return None, None


def cmd_log(args, status):
    path = state_path()
    try:
        data = load_state(path)
    except FileNotFoundError:
        print("No state.json yet — install the TaDa iOS app first. Nothing changed.")
        return 1
    except (OSError, ValueError, StateError) as exc:
        print("Cannot read state.json: %s. Nothing changed." % exc)
        return 1

    if is_stale(data):
        print("Today's doses aren't published yet (file date %s, today %s)."
              % (data.get("date"), today_str()))
        print("Log on the phone or wait for the iOS app to sync. Nothing changed.")
        return 1

    matches = resolve_med(data, args.medication)
    if not matches:
        names = ", ".join(m.get("name", "?") for m in data.get("medications", [])) or "(none today)"
        print("No medication matches %r. Today: %s" % (args.medication, names))
        return 1
    if len(matches) > 1:
        print("Ambiguous %r — matches %s. Be more specific."
              % (args.medication, ", ".join(m.get("name", "?") for m in matches)))
        return 1
    med = matches[0]

    if status == "undo":
        dose = dose_at(med, args.at) if args.at else last_logged(med)
    else:
        dose = dose_at(med, args.at) if args.at else earliest_pending(med)
    if dose is None:
        if args.at:
            label = "PRN" if str(args.at).strip().lower() == "prn" else args.at
            print("No %s dose for %s." % (label, med.get("name")))
        elif status == "undo":
            print("No logged dose to undo for %s." % med.get("name"))
        else:
            print("No pending dose for %s (all logged?). Use --at to pick one." % med.get("name"))
        return 1

    # Re-read immediately before writing and re-apply onto the fresh copy, so a
    # concurrent app/iCloud write to a *different* dose isn't clobbered by our
    # whole-file replace (FR-3: merge by dose key, last-write-wins on logged_at).
    med_id, sched = med.get("id"), dose.get("scheduled_at")
    try:
        fresh = load_state(path)
    except (OSError, ValueError, StateError):
        fresh = None
    if fresh is not None:
        if is_stale(fresh):
            print("state.json rolled to %s while logging. Nothing changed — try again."
                  % fresh.get("date"))
            return 1
        fmed, fdose = find_dose(fresh, med_id, med.get("name"), sched)
        if fdose is None:
            print("That dose changed under us and is gone now. Nothing changed — try again.")
            return 1
        data, med, dose = fresh, fmed, fdose

    if status == "undo":
        dose["status"], dose["logged_at"], dose["source"] = "pending", None, None
        verb = "reset to pending"
    else:
        dose["status"], dose["logged_at"], dose["source"] = status, utc_now(), "plugin"
        verb = "marked " + status
    data["updated_at"] = utc_now()
    data["updated_by"] = "plugin"
    atomic_write(path, data)
    print("%s — %s dose %s. The iOS app will mirror it to Apple Health."
          % (med.get("name"), dose.get("scheduled_at") or "PRN", verb))
    return 0


# --- entry -----------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(prog="tada", description="TaDa Mac companion for the per-dose medication state.json")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("notify", help="notify about overdue pending doses (used by the hook)")
    sub.add_parser("status", help="print today's doses and their status")
    for name, helptext in (("take", "mark a dose Taken"),
                           ("skip", "mark a dose Skipped"),
                           ("undo", "reset a logged dose to pending")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("medication", help="medication name or id (or part of either)")
        sp.add_argument("--at", default=None, metavar="HH:MM|prn",
                        help="target a specific dose: a scheduled HH:MM, or 'prn' for an as-needed dose")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    cmd = args.cmd or "status"
    if cmd == "notify":
        return cmd_notify(args)
    if cmd == "status":
        return cmd_status(args)
    return cmd_log(args, {"take": "taken", "skip": "skipped", "undo": "undo"}[cmd])


if __name__ == "__main__":
    sys.exit(main())
