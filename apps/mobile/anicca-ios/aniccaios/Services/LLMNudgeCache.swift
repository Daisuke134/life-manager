import Foundation
import OSLog

/// LLM生成Nudgeのキャッシュ（@MainActorでスレッド安全性を保証）
@MainActor
final class LLMNudgeCache {
    static let shared = LLMNudgeCache()

    /// 後方互換: 時間のみのキー（problemType_hour）
    private var cacheByHour: [String: LLMGeneratedNudge] = [:]

    /// 新規: 分も含むキー（problemType_hour_minute）- キー衝突防止
    private var cacheByTime: [String: LLMGeneratedNudge] = [:]

    private let logger = Logger(subsystem: "com.anicca.ios", category: "LLMNudgeCache")

    private init() {}

    /// 指定された問題タイプと時刻のNudgeを取得（30分ウィンドウでマッチング）
    func getNudge(for problem: ProblemType, hour: Int, minute: Int = 0) -> LLMGeneratedNudge? {
        // 1. 完全一致を試す（分も含む）
        let exactKey = "\(problem.rawValue)_\(hour)_\(minute)"
        if let nudge = cacheByTime[exactKey] {
            return nudge
        }

        // 2. 30分ウィンドウ内でマッチング
        let targetMinutes = hour * 60 + minute
        for (_, nudge) in cacheByTime where nudge.problemType == problem {
            let nudgeMinutes = nudge.scheduledHour * 60 + nudge.scheduledMinute
            if abs(nudgeMinutes - targetMinutes) <= 30 {
                return nudge
            }
        }

        // 3. 後方互換: 時間のみのキーで検索
        let hourKey = "\(problem.rawValue)_\(hour)"
        return cacheByHour[hourKey]
    }

    /// 指定された問題タイプと時刻のNudgeが存在するか判定（getNudgeのnil判定ラッパー）
    func hasNudge(for problem: ProblemType, hour: Int, minute: Int = 0) -> Bool {
        return getNudge(for: problem, hour: hour, minute: minute) != nil
    }

    /// 指定された問題タイプのNudgeを取得（時刻無視、デバッグ用）
    func getNudgeAnyHour(for problem: ProblemType) -> LLMGeneratedNudge? {
        return cacheByTime.values.first { $0.problemType == problem }
            ?? cacheByHour.values.first { $0.problemType == problem }
    }

    /// Nudgeをキャッシュに設定（複数一括設定）
    func setNudges(_ nudges: [LLMGeneratedNudge]) {
        cacheByHour.removeAll()
        cacheByTime.removeAll()

        for nudge in nudges {
            // 後方互換: 時間のみのキー
            let hourKey = "\(nudge.problemType.rawValue)_\(nudge.scheduledHour)"
            cacheByHour[hourKey] = nudge

            // 新規: 分も含むキー（キー衝突防止）
            let timeKey = "\(nudge.problemType.rawValue)_\(nudge.scheduledHour)_\(nudge.scheduledMinute)"
            cacheByTime[timeKey] = nudge
        }
        logger.info("📦 [LLMCache] Set \(nudges.count) nudges (byHour: \(self.cacheByHour.count), byTime: \(self.cacheByTime.count))")
    }

    /// キャッシュをクリア（テスト用）
    func clear() {
        cacheByHour.removeAll()
        cacheByTime.removeAll()
        logger.info("📦 [LLMCache] Cleared")
    }

    // MARK: - Debug Methods

    /// キャッシュ内のNudge数
    var count: Int { cacheByTime.count }

    /// 最初のNudgeを取得（デバッグ用）
    func getFirstNudge() -> LLMGeneratedNudge? {
        cacheByTime.values.first ?? cacheByHour.values.first
    }

    /// 全キャッシュNudgeを時刻順で取得（デバッグ一覧ビュー用）
    var allCachedNudges: [LLMGeneratedNudge] {
        let nudges = Array(cacheByTime.values)
        return nudges.sorted { lhs, rhs in
            let lhsMinutes = lhs.scheduledHour * 60 + lhs.scheduledMinute
            let rhsMinutes = rhs.scheduledHour * 60 + rhs.scheduledMinute
            return lhsMinutes < rhsMinutes
        }
    }

    /// デバッグ用サマリー
    func debugSummary() -> String {
        if cacheByTime.isEmpty { return "📦 LLMキャッシュ: 空" }
        let entries = cacheByTime.map { "\($0.value.problemType.rawValue)@\($0.value.scheduledTime): \"\($0.value.hook)\"" }
        return "📦 LLMキャッシュ (\(cacheByTime.count)件):\n" + entries.joined(separator: "\n")
    }
}
