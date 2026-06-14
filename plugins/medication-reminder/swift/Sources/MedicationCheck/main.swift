// medication-check — tiny macOS CLI that asks HealthKit whether any medication
// or dietary-supplement sample was logged for "today" (local calendar day).
//
// === DORMANT ===
// As of 2026-04-30, this CLI is NOT in the runtime path. HealthKit on macOS
// is a managed capability that Apple has to grant via a Capability Request,
// and the iOS-only identifiers used below (HKCategoryTypeIdentifierMedicationLog,
// HKCategoryTypeIdentifierDietarySupplement) don't exist in the macOS SDK at
// all — even with the entitlement granted, this code would exit with "no
// recognized medication sample types" on macOS. The plugin's runtime path
// uses an iCloud Drive flag file written by an iOS Shortcut instead.
//
// If/when the Capability Request is approved, the rewrite target on macOS is
// HKMedicationDoseEvent (macOS 26+). See README → "HealthKit on macOS — caveats"
// and project_healthkit_blocked memory note for the full diagnosis.
// =================
//
// Subcommands:
//   --today       returns 0 if anything was logged today, 1 otherwise.
//                 Silent (no stdout). Preserves the original runtime contract.
//   --dump-today  diagnostic probe. Prints one JSON line per sample to stdout:
//                   {"type","start","end","source","metadata"}
//                 Exit codes:
//                   0 — one or more samples emitted
//                   1 — query succeeded, zero samples
//                   2 — HealthKit unavailable / authorization failed / SDK
//                       doesn't recognize the probed identifiers

import Foundation
#if canImport(HealthKit)
import HealthKit
#endif

enum Mode { case today, dumpToday }

let args = CommandLine.arguments
let mode: Mode
if args.contains("--dump-today") {
    mode = .dumpToday
} else if args.contains("--today") {
    mode = .today
} else {
    FileHandle.standardError.write(Data("usage: medication-check [--today|--dump-today]\n".utf8))
    exit(2)
}

// In --today mode we stay silent and exit 1 on any failure (the shell worker
// treats that as "HealthKit couldn't confirm — fall through to the evaluator").
// In --dump-today mode we want loud, human-readable diagnostics.
func fail(_ msg: String) -> Never {
    if mode == .dumpToday {
        FileHandle.standardError.write(Data("medication-check: \(msg)\n".utf8))
        exit(2)
    }
    exit(1)
}

#if !canImport(HealthKit)
fail("HealthKit framework not available on this platform")
#else

guard HKHealthStore.isHealthDataAvailable() else {
    fail("HealthKit data not available on this device")
}

let store = HKHealthStore()

// Neither identifier is documented on macOS; we probe both defensively.
// `categoryType(forIdentifier:)` returns nil if the SDK doesn't know it.
var readTypes = Set<HKObjectType>()
if let t = HKObjectType.categoryType(forIdentifier: .init(rawValue: "HKCategoryTypeIdentifierDietarySupplement")) {
    readTypes.insert(t)
}
if let t = HKObjectType.categoryType(forIdentifier: .init(rawValue: "HKCategoryTypeIdentifierMedicationLog")) {
    readTypes.insert(t)
}

guard !readTypes.isEmpty else {
    fail("no recognized medication sample types on this macOS SDK")
}

do {
    let sema = DispatchSemaphore(value: 0)
    var authError: Error?
    store.requestAuthorization(toShare: [], read: readTypes) { _, error in
        authError = error
        sema.signal()
    }
    sema.wait()
    if let err = authError {
        fail("authorization failed: \(err.localizedDescription)")
    }
}

let calendar = Calendar.current
let startOfDay = calendar.startOfDay(for: Date())
let endOfDay = calendar.date(byAdding: .day, value: 1, to: startOfDay) ?? Date()
let predicate = HKQuery.predicateForSamples(withStart: startOfDay, end: endOfDay, options: .strictStartDate)

let iso = ISO8601DateFormatter()
iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

let outputLock = NSLock()
var totalCount = 0
let group = DispatchGroup()

for type in readTypes {
    guard let sampleType = type as? HKSampleType else { continue }
    group.enter()
    // --today only needs to know "is there at least one?", --dump-today wants them all.
    let limit = (mode == .dumpToday) ? HKObjectQueryNoLimit : 1
    let query = HKSampleQuery(sampleType: sampleType, predicate: predicate, limit: limit, sortDescriptors: nil) { _, samples, _ in
        defer { group.leave() }
        guard let samples = samples else { return }
        for sample in samples {
            outputLock.lock()
            defer { outputLock.unlock() }
            totalCount += 1

            guard mode == .dumpToday else { continue }

            // Coerce metadata into a JSON-safe dict: Date → ISO8601, anything
            // JSONSerialization rejects → its String(describing:) form so we
            // can still see what was there.
            var safeMetadata: Any = NSNull()
            if let md = sample.metadata {
                var dict: [String: Any] = [:]
                for (k, v) in md {
                    if let d = v as? Date {
                        dict[k] = iso.string(from: d)
                    } else if JSONSerialization.isValidJSONObject([k: v]) {
                        dict[k] = v
                    } else {
                        dict[k] = String(describing: v)
                    }
                }
                safeMetadata = dict
            }

            let payload: [String: Any] = [
                "type": sampleType.identifier,
                "start": iso.string(from: sample.startDate),
                "end": iso.string(from: sample.endDate),
                "source": sample.sourceRevision.source.name,
                "metadata": safeMetadata,
            ]
            if let data = try? JSONSerialization.data(withJSONObject: payload, options: []),
               let line = String(data: data, encoding: .utf8) {
                print(line)
            }
        }
    }
    store.execute(query)
}

group.wait()
exit(totalCount > 0 ? 0 : 1)
#endif
