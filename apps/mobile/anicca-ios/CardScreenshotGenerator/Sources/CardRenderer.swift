import SwiftUI
import ImageIO

/// SwiftUI ImageRendererでNudgeカードをPNG画像に変換する
@MainActor
final class CardRenderer {
    let language: String
    let outputDir: URL
    private let locBundle: Bundle

    init(language: String, outputDir: URL) {
        self.language = language
        self.outputDir = outputDir
        self.locBundle = LocalizationBundle.bundle(for: language)
    }

    /// 全189カードの画像を生成
    func generateAllCards() throws -> Int {
        try FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)

        var count = 0
        for problemType in ProblemType.allCases {
            for variantIndex in 0..<problemType.notificationVariantCount {
                _ = try generateCard(problemType: problemType, variantIndex: variantIndex)
                count += 1
            }
        }
        return count
    }

    /// 単一カードの画像を生成
    func generateCard(problemType: ProblemType, variantIndex: Int) throws -> URL {
        let prefix = problemType.rawValue

        // Resolve localized strings using language-specific bundle
        let title = NSLocalizedString(
            "problem_\(prefix)_notification_title", bundle: locBundle, comment: "")
        let notificationText = NSLocalizedString(
            "nudge_\(prefix)_notification_\(variantIndex + 1)", bundle: locBundle, comment: "")
        let detailText = NSLocalizedString(
            "nudge_\(prefix)_detail_\(variantIndex + 1)", bundle: locBundle, comment: "")
        let positiveButtonText = NSLocalizedString(
            "problem_\(prefix)_positive_button", bundle: locBundle, comment: "")

        let view = ExportableNudgeCardView(
            problemType: problemType,
            notificationTitle: title,
            notificationText: notificationText,
            detailText: detailText,
            positiveButtonText: positiveButtonText,
            isAIGenerated: false,
            language: language
        )
        .environment(\.colorScheme, .light)
        .environment(\.locale, language == "ja" ? Locale(identifier: "ja_JP") : Locale(identifier: "en_US"))
        .environment(\.layoutDirection, .leftToRight)

        let renderer = ImageRenderer(content: view)
        renderer.scale = 2.0

        let cardId = "\(problemType.rawValue)_\(variantIndex)"
        let fileURL = outputDir.appendingPathComponent("\(cardId).png")

        guard let image = renderer.cgImage else {
            throw CardRendererError.renderFailed(cardId: cardId)
        }

        let destination = CGImageDestinationCreateWithURL(fileURL as CFURL, "public.png" as CFString, 1, nil)
        guard let destination else {
            throw CardRendererError.writeFailed(path: fileURL.path)
        }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else {
            throw CardRendererError.writeFailed(path: fileURL.path)
        }

        return fileURL
    }
}

enum CardRendererError: Error, LocalizedError {
    case renderFailed(cardId: String)
    case writeFailed(path: String)

    var errorDescription: String? {
        switch self {
        case .renderFailed(let cardId):
            return "Failed to render card: \(cardId)"
        case .writeFailed(let path):
            return "Failed to write PNG: \(path)"
        }
    }
}
