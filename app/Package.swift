// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "VoiceIME",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .executable(name: "VoiceIME", targets: ["VoiceIMEApp"]),
    ],
    targets: [
        .target(
            name: "VoiceIMECore"
        ),
        .executableTarget(
            name: "VoiceIMEApp",
            dependencies: ["VoiceIMECore"]
        ),
        .testTarget(
            name: "VoiceIMETests",
            dependencies: ["VoiceIMECore"],
            resources: [
                .copy("Fixtures"),
            ]
        ),
    ]
)
