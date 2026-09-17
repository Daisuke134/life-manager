import Foundation

/// 1枚画面カードで表示するNudgeコンテンツ
struct NudgeContent: Identifiable {
    let id = UUID()
    let problemType: ProblemType
    let notificationText: String
    let detailText: String
    let variantIndex: Int
    let isAIGenerated: Bool
    let llmNudgeId: String?

    /// 問題タイプから通知文言と詳細文言を取得
    static func content(for problem: ProblemType, variantIndex: Int = 0) -> NudgeContent {
        let messages = notificationMessages(for: problem)
        let details = detailMessages(for: problem)
        let index = variantIndex % max(1, messages.count)

        return NudgeContent(
            problemType: problem,
            notificationText: messages[safe: index] ?? messages[0],
            detailText: details[safe: index] ?? details[0],
            variantIndex: index,
            isAIGenerated: false,
            llmNudgeId: nil
        )
    }

    /// 日付ベースでローテーション
    static func contentForToday(for problem: ProblemType) -> NudgeContent {
        let dayOfYear = Calendar.current.ordinality(of: .day, in: .year, for: Date()) ?? 1
        let messages = notificationMessages(for: problem)
        let index = (dayOfYear - 1) % max(1, messages.count)
        return content(for: problem, variantIndex: index)
    }

    /// LLM生成NudgeからNudgeContentを作成
    static func content(from llmNudge: LLMGeneratedNudge) -> NudgeContent {
        return NudgeContent(
            problemType: llmNudge.problemType,
            notificationText: llmNudge.hook,
            detailText: llmNudge.content,
            variantIndex: -1,  // LLM生成の場合は-1
            isAIGenerated: true,
            llmNudgeId: llmNudge.id
        )
    }
}

// MARK: - Notification Messages
extension NudgeContent {
    /// 通知文言（動的生成 - v1.6.1でバリアント数拡張対応）
    /// ProblemType.notificationVariantCount に基づいて動的にメッセージ配列を生成
    static func notificationMessages(for problem: ProblemType) -> [String] {
        let prefix = problem.rawValue
        return (1...problem.notificationVariantCount).map { i in
            NSLocalizedString("nudge_\(prefix)_notification_\(i)", comment: "")
        }
    }

    /// 1枚画面の詳細説明文（動的生成 - v1.6.1でバリアント数拡張対応）
    /// ProblemType.notificationVariantCount に基づいて動的にメッセージ配列を生成
    static func detailMessages(for problem: ProblemType) -> [String] {
        let prefix = problem.rawValue
        return (1...problem.notificationVariantCount).map { i in
            NSLocalizedString("nudge_\(prefix)_detail_\(i)", comment: "")
        }
    }
}

// MARK: - Safe Array Access
private extension Array {
    subscript(safe index: Int) -> Element? {
        return indices.contains(index) ? self[index] : nil
    }
}
