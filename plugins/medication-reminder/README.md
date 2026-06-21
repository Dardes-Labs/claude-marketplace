# TaDa — companion plugin

Companion Claude Code plugin for **TaDa**, a per-dose medication-adherence system. The core is the TaDa **iOS app**; this plugin is the Mac surface. It reads the per-dose `state.json` the app syncs through iCloud Drive, nudges you (macOS notification) about scheduled doses you haven't logged, and lets you mark a dose **Taken** or **Skipped** from the Mac.

Built because ADHD + "just remember to take it" don't mix.

> [!IMPORTANT]
> **This README describes the TaDa target, not the shipped code.** The scripts in this directory still implement the **legacy** model — a single per-day iCloud flag (`taken_YYYY-MM-DD`), a `medications.toml` config, a Python priority evaluator, and a dormant Swift HealthKit CLI. The rewrite to the per-dose `state.json` model below ships with the `medication-reminder` → `tada` rename. Design source of truth: [`tada-medication-sync.md`](../../.claude/prds/tada-medication-sync.md).

---

## What it does

- **Reads per-dose state.** The TaDa iOS app reads your medication schedule from Apple Health and writes a per-dose `state.json` into iCloud Drive. This plugin reads it — there is no local config.
- **Nudges on pending doses.** At SessionStart it checks today's doses and sends a macOS notification for any still `pending` past their scheduled time. Done for the day → silent.
- **Logs from the Mac.** Mark a dose **Taken** or **Skipped** from the Mac and the plugin writes the status back into `state.json` (`source: "plugin"`). The iOS app picks that up and mirrors it into Apple Health — the plugin itself **never touches HealthKit**.
- **Config-less + app-dependent.** The medication list and schedule come entirely from `state.json`. Without the iOS app nothing produces state, so the plugin is inert.

---

## How it works (target flow)

```
SessionStart hook
    └── read  iCloud/MedicationCheck/state.json
            └── for each medication → each dose scheduled for today:
                    pending and past scheduled_at  → macOS notification
                    taken / skipped                → silent
Mark from Mac (Taken / Skipped)
    └── write dose status + logged_at + source:"plugin" back to state.json
            └── iOS app mirrors the dose into Apple Health (HKMedicationDoseEvent)
```

Non-blocking by design: the SessionStart hook detaches its worker and returns instantly, so a session is never delayed. If iCloud isn't reachable it simply no-ops until the file is available.

---

## The sync contract

State lives at `~/Library/Mobile Documents/com~apple~CloudDocs/MedicationCheck/state.json`, read **and** written by both surfaces. Each dose is keyed by `(medication id, date, scheduled_at)`; `status` ∈ `taken` / `skipped` / `pending`; conflicts resolve by **last-write-wins on `logged_at`**; `source` (`ios-app` / `widget` / `plugin` / `apple-health`) tells the app what to mirror and prevents loops. Medication `id` is the primary key (`healthkit:<medicationConceptIdentifier>`); `name` is display-only. Full versioned schema (`schema_version: "1.0"`): **FR-6** of [`tada-medication-sync.md`](../../.claude/prds/tada-medication-sync.md).

---

## Why the Mac plugin never touches HealthKit

By design the **iOS app is the sole HealthKit writer**; the Mac plugin works only through `state.json`. That isn't a stopgap — HealthKit on macOS is doubly gated (verified 2026-04-30):

1. **Capability gating.** HealthKit isn't in [Apple's macOS supported-capabilities list](https://developer.apple.com/help/account/reference/supported-capabilities-macos/) — for a macOS App ID the standard capability checkbox is disabled. The only path is an Apple-reviewed **Capability Request**, granted per-app and not guaranteed.
2. **Signing / AMFI.** `com.apple.developer.healthkit` is a *restricted* entitlement; macOS `amfid` SIGKILLs ad-hoc-signed binaries that carry it — so it needs a fully provisioned, signed app, not a hook-invoked CLI.

The medication types do exist in the macOS 26 SDK (`HKMedicationDoseEvent`, `HKMedicationConcept`, `HKUserAnnotatedMedication`) — the framework is there, only the entitlement is gated. On iOS both entitlements are self-service, which is why the app owns the HealthKit side. (The dormant legacy Swift CLI at `swift/Sources/MedicationCheck/main.swift` predates this decision and is slated for removal in the rewrite.)

---

## Install

```
/plugin marketplace add agnislav-o/claude-marketplace
/plugin install medication-reminder@dardes
```

You also need the **TaDa iOS app**, signed into the same iCloud account — it's what produces `state.json`. (The legacy `install.sh` seeds a `medications.toml`; that step goes away in the rewrite.)

---

## Environment variables (target)

| Var | Default | Purpose |
| --- | --- | --- |
| `MEDICATION_ICLOUD_DIR` | `~/Library/Mobile Documents/com~apple~CloudDocs/MedicationCheck` | iCloud Drive folder holding `state.json` |
| `MEDICATION_STATE_DIR` | `~/.medication` | Local worker scratch + log |
| `MEDICATION_LOG_FILE` | `$MEDICATION_STATE_DIR/check.log` | Worker log (nohup) |

`MEDICATION_CONFIG` / `medications.toml` is removed — the plugin is config-less.
