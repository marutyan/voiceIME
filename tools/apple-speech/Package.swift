// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "apple-speech",
    platforms: [
        .macOS("26.0"),
    ],
    products: [
        .executable(name: "apple-transcribe", targets: ["AppleTranscribe"]),
        .executable(name: "record-prompts", targets: ["RecordPrompts"]),
    ],
    targets: [
        .target(
            name: "AppleSpeechSupport"
        ),
        .executableTarget(
            name: "AppleTranscribe",
            dependencies: ["AppleSpeechSupport"]
        ),
        .executableTarget(
            name: "RecordPrompts",
            dependencies: ["AppleSpeechSupport"]
        ),
        .testTarget(
            name: "AppleSpeechTests",
            dependencies: [
                "AppleSpeechSupport",
                "AppleTranscribe",
                "RecordPrompts",
            ]
        ),
    ]
)
