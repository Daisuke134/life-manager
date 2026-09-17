import Foundation
import OSLog

/// Nudge統計データ
struct NudgeStats: Codable, Equatable {
    let problemType: String
    let variantIndex: Int
    let scheduledHour: Int

    var tappedCount: Int = 0
    var ignoredCount: Int = 0
    var thumbsUpCount: Int = 0
    var thumbsDownCount: Int = 0
    var consecutiveIgnoredDays: Int = 0
    var lastTappedDate: Date?
    var lastScheduledDate: Date?

    /// tap率を計算
    var tapRate: Double {
        let total = tappedCount + ignoredCount
        guard total > 0 else { return 0.5 }
        return Double(tappedCount) / Double(total)
    }

    /// 👍率を計算
    var thumbsUpRate: Double {
        let total = thumbsUpCount + thumbsDownCount
        guard total > 0 else { return 0.5 }
        return Double(thumbsUpCount) / Double(total)
    }

    /// 総サンプル数
    var totalSamples: Int {
        tappedCount + ignoredCount
    }

    /// 一意キー
    var key: String {
        "\(problemType)_\(variantIndex)_\(scheduledHour)"
    }
}

/// スケジュールされたNudge（ignored判定用）
struct ScheduledNudge: Codable {
    let problemType: String
    let variantIndex: Int
    let scheduledHour: Int
    let scheduledDate: Date
    var wasTapped: Bool = false
}

/// Nudge統計管理
@MainActor
final class NudgeStatsManager {
    static let shared = NudgeStatsManager()

    private let logger = Logger(subsystem: "com.anicca.ios", category: "NudgeStats")
    private let queue = DispatchQueue(label: "com.anicca.nudgeStats", qos: .utility)

    // Storage keys
    private let statsKey = "com.anicca.nudgeStats"
    private let scheduledKey = "com.anicca.scheduledNudges"
    
    // Phase 5: 設定可能な閾値
    #if DEBUG
    private static let ignoredThresholdMinutes: Int = 1     // デバッグ: 1分（テスト用）
    #else
    private static let ignoredThresholdMinutes: Int = 15    // 本番: 15分
    #endif
    private static let unresponsiveThresholdDays: Int = 7   // 7日連続ignoredで完全無反応と判定

    // In-memory cache
    private var stats: [String: NudgeStats] = [:]
    private var scheduledNudges: [String: ScheduledNudge] = [:]

    private init() {
        loadFromStorage()
    }

    // MARK: - Public API

    /// 通知スケジュール成功時に記録
    /// - Parameter fireDate: 通知の実際の配信予定時刻。`Date()` ではなく配信時刻を渡すこと。
    func recordScheduled(problemType: String, variantIndex: Int, scheduledHour: Int, isAIGenerated: Bool = false, llmNudgeId: String? = nil, fireDate: Date? = nil) {
        let key = "\(problemType)_\(variantIndex)_\(scheduledHour)"
        let nudge = ScheduledNudge(
            problemType: problemType,
            variantIndex: variantIndex,
            scheduledHour: scheduledHour,
            scheduledDate: fireDate ?? Date()
        )
        scheduledNudges[key] = nudge

        // statsも更新
        var stat = stats[key] ?? NudgeStats(problemType: problemType, variantIndex: variantIndex, scheduledHour: scheduledHour)
        stat.lastScheduledDate = Date()
        stats[key] = stat

        saveToStorage()
        logger.info("Recorded scheduled: \(key) isAIGenerated:\(isAIGenerated)")
    }

    /// 通知タップ時に記録
    func recordTapped(problemType: String, variantIndex: Int, scheduledHour: Int, isAIGenerated: Bool = false, llmNudgeId: String? = nil) {
        let key = "\(problemType)_\(variantIndex)_\(scheduledHour)"

        // scheduledNudgesを更新
        if var nudge = scheduledNudges[key] {
            nudge.wasTapped = true
            scheduledNudges[key] = nudge
        }

        // statsを更新
        var stat = stats[key] ?? NudgeStats(problemType: problemType, variantIndex: variantIndex, scheduledHour: scheduledHour)
        stat.tappedCount += 1
        stat.consecutiveIgnoredDays = 0  // リセット
        stat.lastTappedDate = Date()
        stats[key] = stat

        saveToStorage()
        logger.info("Recorded tapped: \(key), tapRate: \(stat.tapRate), isAIGenerated:\(isAIGenerated)")

        // Mixpanelに送信
        AnalyticsManager.shared.track(.nudgeTapped, properties: [
            "problem_type": problemType,
            "variant_index": variantIndex,
            "scheduled_hour": scheduledHour,
            "is_ai_generated": isAIGenerated,
            "llm_nudge_id": llmNudgeId ?? ""
        ])
    }

    /// ignored判定（アプリ起動時に呼び出す）
    func checkAndRecordIgnored() async {
        let now = Date()
        let calendar = Calendar.current

        for (key, nudge) in scheduledNudges {
            // ignoredThresholdMinutes以上前 & 未tapped = ignored
            guard !nudge.wasTapped,
                  let minutesDiff = calendar.dateComponents([.minute], from: nudge.scheduledDate, to: now).minute,
                  minutesDiff >= Self.ignoredThresholdMinutes else {
                continue
            }

            recordIgnored(
                problemType: nudge.problemType,
                variantIndex: nudge.variantIndex,
                scheduledHour: nudge.scheduledHour
            )

            // Mixpanelに送信
            AnalyticsManager.shared.track(.nudgeIgnored, properties: [
                "problem_type": nudge.problemType,
                "variant_index": nudge.variantIndex,
                "scheduled_hour": nudge.scheduledHour
            ])

            // scheduledNudgesから削除
            scheduledNudges.removeValue(forKey: key)
        }

        saveToStorage()
    }

    /// ignored記録
    private func recordIgnored(problemType: String, variantIndex: Int, scheduledHour: Int) {
        let key = "\(problemType)_\(variantIndex)_\(scheduledHour)"

        var stat = stats[key] ?? NudgeStats(problemType: problemType, variantIndex: variantIndex, scheduledHour: scheduledHour)
        stat.ignoredCount += 1
        stat.consecutiveIgnoredDays += 1
        stats[key] = stat

        logger.info("Recorded ignored: \(key), consecutiveIgnoredDays: \(stat.consecutiveIgnoredDays)")
    }

    /// 👍記録
    func recordThumbsUp(problemType: String, variantIndex: Int) {
        // scheduledHourは不明なので、全時間帯の同じvariantを更新
        for (key, var stat) in stats {
            if stat.problemType == problemType && stat.variantIndex == variantIndex {
                stat.thumbsUpCount += 1
                stats[key] = stat
            }
        }
        saveToStorage()

        AnalyticsManager.shared.track(.nudgePositiveFeedback, properties: [
            "problem_type": problemType,
            "variant_index": variantIndex
        ])
    }

    /// 👎記録
    func recordThumbsDown(problemType: String, variantIndex: Int) {
        for (key, var stat) in stats {
            if stat.problemType == problemType && stat.variantIndex == variantIndex {
                stat.thumbsDownCount += 1
                stats[key] = stat
            }
        }
        saveToStorage()

        AnalyticsManager.shared.track(.nudgeNegativeFeedback, properties: [
            "problem_type": problemType,
            "variant_index": variantIndex
        ])
    }

    /// 統計取得
    func getStats(problemType: String, variantIndex: Int, hour: Int) -> NudgeStats? {
        let key = "\(problemType)_\(variantIndex)_\(hour)"
        return stats[key]
    }

    /// 問題タイプの全バリアント統計取得
    func getAllStats(for problemType: String, hour: Int) -> [NudgeStats] {
        return stats.values.filter { $0.problemType == problemType && $0.scheduledHour == hour }
    }

    /// 時間帯の連続ignored日数取得
    func getConsecutiveIgnoredDays(problemType: String, hour: Int) -> Int {
        let hourStats = stats.values.filter { $0.problemType == problemType && $0.scheduledHour == hour }
        return hourStats.map { $0.consecutiveIgnoredDays }.max() ?? 0
    }
    
    // MARK: - Day 1 Detection

    /// Day1判定: オンボーディングから0日目（v1.6.1: 日数ベースに統一）
    /// Day-Cyclingと同じ基準を使用し、ユーザーの行動に依存しない
    func isDay1(for problemType: String) -> Bool {
        return getDaysSinceOnboarding(for: problemType) == 0
    }
    
    /// 旧Day1判定（後方互換性のため残す）: インタラクション記録がない
    @available(*, deprecated, message: "Use isDay1(for:) which uses getDaysSinceOnboarding")
    func isDay1ByInteraction(for problemType: String) -> Bool {
        let problemStats = stats.values.filter { $0.problemType == problemType }
        return problemStats.allSatisfy { $0.totalSamples == 0 }
    }

    // MARK: - Phase 5: Unresponsive User Handling
    
    /// 完全無反応ユーザー判定
    /// 全バリアントで7日以上連続ignoredの場合にtrue
    func isCompletelyUnresponsive(for problemType: String, hour: Int) -> Bool {
        let hourStats = stats.values.filter { $0.problemType == problemType && $0.scheduledHour == hour }
        
        // 統計がなければ無反応ではない（まだ試していない）
        guard !hourStats.isEmpty else { return false }
        
        // 全バリアントが閾値以上の連続ignoredならtrue
        let minConsecutive = hourStats.map { $0.consecutiveIgnoredDays }.min() ?? 0
        return minConsecutive >= Self.unresponsiveThresholdDays
    }
    
    /// 未試行バリアントを選択
    /// 統計がないバリアント、またはサンプル数が最小のバリアントを返す
    func selectUntriedVariant(for problemType: String, hour: Int, availableVariants: [Int]) -> Int? {
        // 各バリアントのサンプル数を取得
        var variantSamples: [(index: Int, samples: Int)] = []
        
        for variantIndex in availableVariants {
            let key = "\(problemType)_\(variantIndex)_\(hour)"
            let samples = stats[key]?.totalSamples ?? 0
            variantSamples.append((variantIndex, samples))
        }
        
        // サンプル数0のバリアントがあればランダムで選択
        let untriedVariants = variantSamples.filter { $0.samples == 0 }
        if !untriedVariants.isEmpty {
            logger.info("Found \(untriedVariants.count) untried variants for \(problemType)")
            return untriedVariants.randomElement()?.index
        }
        
        // なければサンプル数最小のバリアントを選択
        if let minSamples = variantSamples.min(by: { $0.samples < $1.samples }) {
            logger.info("Selecting least tested variant \(minSamples.index) with \(minSamples.samples) samples")
            return minSamples.index
        }
        
        return nil
    }
    
    /// 特定バリアントの統計をリセット（デバッグ用）
    func resetVariantStats(problemType: String, variantIndex: Int, hour: Int) {
        let key = "\(problemType)_\(variantIndex)_\(hour)"
        stats.removeValue(forKey: key)
        saveToStorage()
        logger.info("Reset stats for \(key)")
    }

    // MARK: - Day-Cycling Support (v1.6.1)

    private let onboardingDateKey = "com.anicca.onboardingDate"

    /// オンボーディング完了日からの経過日数を取得
    /// - Returns: 経過日数（0 = 今日がオンボーディング日）
    func getDaysSinceOnboarding(for problemType: String) -> Int {
        let key = "\(onboardingDateKey)_\(problemType)"
        let defaults = UserDefaults.standard

        guard let startDate = defaults.object(forKey: key) as? Date else {
            // 初回: 今日を記録してDay 0を返す
            defaults.set(Date(), forKey: key)
            logger.info("Day-Cycling: First day for \(problemType), recording onboarding date")
            return 0
        }

        let calendar = Calendar.current
        let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: startDate), to: calendar.startOfDay(for: Date())).day ?? 0
        return max(0, days)
    }
    
    /// Day-Cyclingのオンボーディング日をリセット（問題タイプ変更時）
    /// - Parameter problemType: リセットする問題タイプ
    func resetOnboardingDateForProblem(_ problemType: String) {
        let key = "\(onboardingDateKey)_\(problemType)"
        UserDefaults.standard.removeObject(forKey: key)
        logger.info("Day-Cycling: Reset onboarding date for \(problemType)")
    }
    
    /// 全問題タイプのオンボーディング日をリセット（ログアウト時）
    func resetAllOnboardingDates() {
        let defaults = UserDefaults.standard
        for problem in ProblemType.allCases {
            let key = "\(onboardingDateKey)_\(problem.rawValue)"
            defaults.removeObject(forKey: key)
        }
        logger.info("Day-Cycling: Reset all onboarding dates")
    }

    // MARK: - Storage

    private func loadFromStorage() {
        let defaults = UserDefaults.standard

        if let data = defaults.data(forKey: statsKey),
           let decoded = try? JSONDecoder().decode([String: NudgeStats].self, from: data) {
            stats = decoded
        }

        if let data = defaults.data(forKey: scheduledKey),
           let decoded = try? JSONDecoder().decode([String: ScheduledNudge].self, from: data) {
            scheduledNudges = decoded
        }
    }

    private func saveToStorage() {
        queue.async { [stats, scheduledNudges] in
            let defaults = UserDefaults.standard

            if let data = try? JSONEncoder().encode(stats) {
                defaults.set(data, forKey: self.statsKey)
            }

            if let data = try? JSONEncoder().encode(scheduledNudges) {
                defaults.set(data, forKey: self.scheduledKey)
            }
        }
    }

    // MARK: - Debug

    #if DEBUG
    func resetAllStats() {
        stats = [:]
        scheduledNudges = [:]
        saveToStorage()
        logger.info("All stats reset")
    }

    /// DEBUG用: 指定回数のignoredを強制記録
    func debugRecordIgnored(problemType: String, variantIndex: Int, scheduledHour: Int, count: Int) {
        let key = "\(problemType)_\(variantIndex)_\(scheduledHour)"

        var stat = stats[key] ?? NudgeStats(problemType: problemType, variantIndex: variantIndex, scheduledHour: scheduledHour)

        for _ in 0..<count {
            stat.ignoredCount += 1
            stat.consecutiveIgnoredDays += 1
        }

        stats[key] = stat
        saveToStorage()
        logger.info("DEBUG: Recorded \(count) ignored for \(problemType), consecutiveIgnoredDays: \(stat.consecutiveIgnoredDays)")
    }

    /// DEBUG用: オンボーディング日をリセット
    func resetOnboardingDate(for problemType: String) {
        let key = "\(onboardingDateKey)_\(problemType)"
        UserDefaults.standard.removeObject(forKey: key)
        logger.info("DEBUG: Reset onboarding date for \(problemType)")
    }

    /// DEBUG用: オンボーディング日を過去に設定
    func setOnboardingDate(for problemType: String, daysAgo: Int) {
        let key = "\(onboardingDateKey)_\(problemType)"
        let pastDate = Calendar.current.date(byAdding: .day, value: -daysAgo, to: Date()) ?? Date()
        UserDefaults.standard.set(pastDate, forKey: key)
        logger.info("DEBUG: Set onboarding date for \(problemType) to \(daysAgo) days ago")
    }
    #endif
}

