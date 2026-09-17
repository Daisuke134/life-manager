import Foundation
import UserNotifications
import OSLog

/// 通知スケジューラ（スリム版）
/// - 認証リクエスト
/// - カテゴリ登録
/// - サーバー駆動型Nudge通知
@MainActor
final class NotificationScheduler {
    static let shared = NotificationScheduler()

    enum Category: String {
        case nudge = "NUDGE"
    }

    enum Action: String {
        case startConversation = "START_CONVERSATION"
        case dismissAll = "DISMISS_ALL"
    }

    private let center = UNUserNotificationCenter.current()
    private let logger = Logger(subsystem: "com.anicca.ios", category: "NotificationScheduler")

    private init() {}

    // MARK: - Localization Helper

    private func localizedString(_ key: String, comment: String = "") -> String {
        let language = AppState.shared.userProfile.preferredLanguage
        guard let path = Bundle.main.path(forResource: language.rawValue, ofType: "lproj"),
              let bundle = Bundle(path: path) else {
            return NSLocalizedString(key, comment: comment)
        }
        return NSLocalizedString(key, tableName: nil, bundle: bundle, value: key, comment: comment)
    }

    // MARK: - Authorization

    @discardableResult
    func requestAuthorization() async -> Bool {
        do {
            var options: UNAuthorizationOptions = [.alert, .sound, .badge]
            if #available(iOS 15.0, *) {
                options.insert(.timeSensitive)
            }
            let notificationsGranted = try await center.requestAuthorization(options: options)
            return notificationsGranted
        } catch {
            logger.error("Notification authorization error: \(error.localizedDescription, privacy: .public)")
            return false
        }
    }

    @discardableResult
    func requestAuthorizationIfNeeded() async -> Bool {
        let settings = await center.notificationSettings()
        switch settings.authorizationStatus {
        case .notDetermined:
            return await requestAuthorization()
        case .authorized, .provisional, .ephemeral:
            return true
        default:
            return false
        }
    }

    func isAuthorizedForAlerts() async -> Bool {
        let settings = await center.notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            return true
        default:
            return false
        }
    }

    // MARK: - Categories

    func registerCategories() {
        let start = UNNotificationAction(
            identifier: Action.startConversation.rawValue,
            title: localizedString("notification_action_start_conversation"),
            options: [.foreground]
        )

        let dismiss = UNNotificationAction(
            identifier: Action.dismissAll.rawValue,
            title: localizedString("notification_action_dismiss"),
            options: [.destructive]
        )

        let nudgeCategory = UNNotificationCategory(
            identifier: Category.nudge.rawValue,
            actions: [start, dismiss],
            intentIdentifiers: [],
            options: [.customDismissAction]
        )

        let problemNudgeCategory = UNNotificationCategory(
            identifier: ProblemNotificationScheduler.Category.problemNudge.rawValue,
            actions: [start, dismiss],
            intentIdentifiers: [],
            options: [.customDismissAction]
        )

        center.setNotificationCategories([nudgeCategory, problemNudgeCategory])
    }

    // v1.8.7: local daily-affirmation scheduling removed. Affirmations are delivered
    // remotely via APNs (backend), so there is no on-device scheduling here.
}
