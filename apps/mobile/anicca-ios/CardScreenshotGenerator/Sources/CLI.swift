import Foundation
import ArgumentParser

@main
struct CardScreenshotGenerator: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        abstract: "Generate PNG screenshots of all Nudge cards for TikTok posting"
    )

    @Option(name: .shortAndLong, help: "Language code (en or ja)")
    var language: String = "en"

    @Option(name: .shortAndLong, help: "Output directory (repo root relative)")
    var output: String

    @Flag(help: "Generate only one card for testing")
    var testMode: Bool = false

    mutating func run() async throws {
        guard language == "en" || language == "ja" else {
            throw ValidationError("Language must be 'en' or 'ja'")
        }

        let outputURL = URL(fileURLWithPath: output, isDirectory: true)
        let lang = language
        let isTest = testMode
        let outPath = output

        if isTest {
            let url = try await MainActor.run {
                let renderer = CardRenderer(language: lang, outputDir: outputURL)
                return try renderer.generateCard(problemType: .stayingUpLate, variantIndex: 0)
            }
            print("Test card generated: \(url.path)")
        } else {
            let count = try await MainActor.run {
                let renderer = CardRenderer(language: lang, outputDir: outputURL)
                return try renderer.generateAllCards()
            }
            print("Generated \(count) cards in \(outPath)")
        }
    }
}
