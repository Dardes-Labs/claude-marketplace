// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "medication-check",
    platforms: [
        .macOS(.v13)
    ],
    targets: [
        .executableTarget(
            name: "MedicationCheck",
            path: "Sources/MedicationCheck"
        )
    ]
)
