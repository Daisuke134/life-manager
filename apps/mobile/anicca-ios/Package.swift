// swift-tools-version: 5.9
import PackageDescription

// CardScreenshotGenerator: macOS CLI for generating Nudge card PNG images.
// This package coexists with aniccaios.xcodeproj — Xcode uses the .xcodeproj,
// `swift build` / `swift run` use this Package.swift.
//
// Single-target design: all source files (shared models + CLI) are in one module,
// avoiding public/internal visibility issues between SPM targets.
//
// Usage:
//   cd aniccaios
//   swift run CardScreenshotGenerator --language en --output ../assets/card-screenshots/en
//   swift run CardScreenshotGenerator --language ja --output ../assets/card-screenshots/ja
//   swift run CardScreenshotGenerator --language en --output /tmp/test --test-mode

let package = Package(
    name: "AniccaCardTools",
    defaultLocalization: "en",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(url: "https://github.com/apple/swift-argument-parser", from: "1.3.0"),
    ],
    targets: [
        .executableTarget(
            name: "CardScreenshotGenerator",
            dependencies: [
                .product(name: "ArgumentParser", package: "swift-argument-parser"),
            ],
            path: ".",
            exclude: [
                "build",
                "aniccaios/Resources/de.lproj",
                "aniccaios/Resources/es.lproj",
                "aniccaios/Resources/fr.lproj",
                "aniccaios/Resources/pt-BR.lproj",
            ],
            sources: [
                // CLI sources
                "CardScreenshotGenerator/Sources/CLI.swift",
                "CardScreenshotGenerator/Sources/CardRenderer.swift",
                "CardScreenshotGenerator/Sources/ExportableNudgeCardView.swift",
                "CardScreenshotGenerator/Sources/LocalizationHelper.swift",
                // Shared models/views from iOS app (subset needed for card rendering)
                "aniccaios/Models/ProblemType.swift",
                "aniccaios/Models/NudgeContent.swift",
                "aniccaios/Models/LLMGeneratedNudge.swift",
                "aniccaios/Views/NudgeCardContent.swift",
                "aniccaios/DesignSystem/AppTheme.swift",
            ],
            // en.lproj and ja.lproj are auto-discovered by SPM from path "."
            // Others excluded above to avoid unnecessary localization bundles
        ),
    ]
)
