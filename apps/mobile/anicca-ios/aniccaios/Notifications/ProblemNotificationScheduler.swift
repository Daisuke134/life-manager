import Foundation
import UserNotifications
import OSLog

/// テスト用プロトコル
protocol ProblemNotificationSchedulerProtocol {
    func scheduleNotifications(for problems: [String]) async
}

/// 問題ベースの通知スケジューラ（スリム版）
///
/// v1.8.7: 通知はリモート（APNs）配信に移行済み。ローカルの problem-nudge スケジューラは廃止された。
/// このクラスは「既存ビルドからのアップグレードで残った古いローカル通知を掃除する」ためだけに存続する。
/// （PushTokenService / AppState から `scheduleNotifications(for:)` / `cancelAllNotifications()` が呼ばれる）
final class ProblemNotificationScheduler: ProblemNotificationSchedulerProtocol {
    static let shared = ProblemNotificationScheduler()

    private let center = UNUserNotificationCenter.current()
    private let logger = Logger(subsystem: "com.anicca.ios", category: "ProblemNotificationScheduler")

    /// 通知カテゴリID
    enum Category: String {
        case problemNudge = "PROBLEM_NUDGE"
    }

    /// Phase 5: 最大シフト量（分）- 2時間まで
    private let maxShiftMinutes = 120

    private init() {}

    // MARK: - Public API

    /// v1.8.7: notifications are remote-only (APNs). The local problem-nudge scheduler
    /// is retired. Clear any previously-scheduled local nudges (free + problem) so old
    /// builds upgrading in place stop firing locally, and schedule nothing further.
    func scheduleNotifications(for problems: [String]) async {
        _ = problems
        let freeIds = (0..<3).map { "free_nudge_\($0)" }
        center.removePendingNotificationRequests(withIdentifiers: freeIds)
        await removeAllProblemNotifications()
    }

    /// すべての問題通知をキャンセル
    func cancelAllNotifications() async {
        await removeAllProblemNotifications()
    }

    // MARK: - Private Methods

    private func removeAllProblemNotifications() async {
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            center.getPendingNotificationRequests { requests in
                let identifiers = requests
                    .map(\.identifier)
                    .filter { $0.hasPrefix("PROBLEM_") }
                if !identifiers.isEmpty {
                    self.center.removePendingNotificationRequests(withIdentifiers: identifiers)
                }
                continuation.resume()
            }
        }
    }

    // MARK: - Wake Window Detection

    /// cant_wake_upの起床ウィンドウ（06:00-06:30）かどうか判定
    func isWakeWindow(problem: ProblemType, hour: Int, minute: Int) -> Bool {
        guard problem == .cantWakeUp else { return false }
        let totalMinutes = hour * 60 + minute
        return totalMinutes >= 360 && totalMinutes <= 390 // 06:00-06:30
    }

    // MARK: - Phase 5: Shift Calculation (Testable)

    /// シフト量を計算（純粋関数、テスト可能）
    /// - Parameters:
    ///   - currentShift: 現在のシフト量（分）
    ///   - consecutiveIgnored: 連続無視日数
    /// - Returns: 新しいシフト量（分）、最大 maxShiftMinutes まで
    func calculateNewShift(currentShift: Int, consecutiveIgnored: Int) -> Int {
        guard consecutiveIgnored >= 2 else { return currentShift }
        return min(currentShift + 30, maxShiftMinutes)
    }
}
