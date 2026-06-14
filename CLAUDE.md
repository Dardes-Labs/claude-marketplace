# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo overview

This is **`dardes`**, a personal Claude Code plugin marketplace. It is not a single application — it is a registry whose only job is to host plugins under `plugins/<name>/` and advertise them via `.claude-plugin/marketplace.json` at the repo root.

To add a plugin: create `plugins/<name>/.claude-plugin/plugin.json`, then add a source entry to `.claude-plugin/marketplace.json`. Each plugin is independently versioned and self-contained — never share code between plugins by reaching across `plugins/<a>/` and `plugins/<b>/`.

Currently the only plugin is `medication-reminder`. The marketplace owner identity (`agnislav-o`, contact in `marketplace.json`) is the same per-plugin author identity used in each plugin's `plugin.json`.

## medication-reminder plugin — what's load-bearing

This plugin's design rests on a non-obvious architectural decision that any future change must respect:

**HealthKit on macOS is gated and not in the runtime path.** Apple's macOS supported-capabilities list does not include HealthKit — enabling it requires a per-app Apple Capability Request that has to be approved (verified 2026-04-30). The Swift HealthKit CLI at `plugins/medication-reminder/swift/Sources/MedicationCheck/main.swift` is therefore **dormant** — it is intentionally not invoked by `medication-check.sh`, and `install.sh` no longer builds it. The header comment in that file states the conditions under which it could be re-lit (capability grant + rewrite from iOS-only `HKCategoryTypeIdentifierMedicationLog` to the macOS-26 `HKMedicationDoseEvent`). Do not try to "fix" the Swift CLI by ad-hoc signing or by self-service entitlements — those paths were investigated and ruled out.

**The shipping architecture (Plan B):** an iOS Shortcut writes a zero-byte flag file `taken_YYYY-MM-DD` into `iCloud Drive/MedicationCheck/`; the macOS worker reads that flag. Same pattern Health Auto Export and similar Mac apps use for Health-on-Mac in absence of HealthKit access.

**SessionStart hook flow.** `hooks/hooks.json` registers `scripts/session-start.sh` for the `SessionStart` event. `session-start.sh` detaches `scripts/medication-check.sh` via `nohup ... >>$LOG_FILE 2>&1 &; disown` and returns exit 0 within a few hundred ms. **Never let the hook block** — Claude Code waits for it before continuing. The detached worker checks (1) the local `~/.medication/taken_YYYY-MM-DD` flag, (2) the iCloud-synced flag, and only if both are missing does it invoke the priority evaluator. On iCloud-flag hit, the worker copies it to local for fast-path on subsequent runs.

**`evaluate()` in `scripts/evaluate-priority.py` is a deliberate stub.** It raises `NotImplementedError` and the worker swallows that. This is the reserved user-contribution slot for the priority/timing logic — owner's ADHD-experience judgment shapes it. Don't implement it without explicit instruction; the empty stub is the expected state.

**Per-medication state is coarse-grained.** Both flag files are date-keyed only — no per-med suffix. Documented as a known gap in the plugin README; if the iOS bridge described in conversation history gets built, it'll replace the binary flag with a `state.json` carrying per-med adherence.

## Common commands

All run from `plugins/medication-reminder/` unless noted.

```bash
./install.sh                       # idempotent — seeds ~/.medication/medications.toml and iCloud Drive folder
./scripts/medication-check.sh      # run the worker directly (for testing)
time ./scripts/session-start.sh    # verify the hook returns in <1s
tail -5 ~/.medication/check.log    # inspect worker output

# Manually mark today done — local only:
touch ~/.medication/taken_$(date +%Y-%m-%d)

# Manually mark today done — iCloud-synced (propagates to other Macs):
touch "$HOME/Library/Mobile Documents/com~apple~CloudDocs/MedicationCheck/taken_$(date +%Y-%m-%d)"
```

There is no test suite, lint config, or build step. The Swift package compiles but is not part of any workflow.

## Project management workflow (ccpm)

The `/ccpm` skill is installed at `.claude/skills/ccpm/` and provides a PRD → epic → tasks → GitHub-issues workflow. Planning artifacts go in `.claude/prds/` and `.claude/epics/`. Helper scripts (status, standup, search, validate, etc.) live in `.claude/skills/ccpm/references/scripts/` and should be invoked directly for read-only/reporting work — see the skill's "Script-First Rule".

The repo currently has no `git remote` configured. Until one is added, ccpm's `sync` and `execute` phases are no-ops; `plan` and `structure` work locally. Don't push fixes to the no-remote warning — it's expected state.

## Configuration

Each medication in `~/.medication/medications.toml` has `name`, `priority` (`crucial`/`important`/`optional`), optional `take` (window keyword or `HH:MM`), optional `deadline` (hard cut-off), and optional `note`. The full schema and window definitions are in `plugins/medication-reminder/config/medications.example.toml` — keep that file and the `TAKE_WINDOWS` dict in `evaluate-priority.py` in sync.
