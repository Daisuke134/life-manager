// v1.8.2 — Singular SDK 再統合 + RevenueCat→Singular→TikTok SAN
import UIKit
import UserNotifications
import OSLog
import BackgroundTasks
import RevenueCat

class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        let proxy = Bundle.main.object(forInfoDictionaryKey: "ANICCA_PROXY_BASE_URL") as? String ?? "nil"
        print("ANICCA_PROXY_BASE_URL =", proxy)

        let resetFlag = (Bundle.main.object(forInfoDictionaryKey: "RESET_ON_LAUNCH") as? NSString)?.boolValue == true
        let shouldReset = resetFlag || ProcessInfo.processInfo.arguments.contains("-resetOnLaunch")
        if shouldReset {
            UserDefaults.standard.removePersistentDomain(forName: Bundle.main.bundleIdentifier ?? "")
            UserDefaults.standard.synchronize()
            AppState.shared.resetState()
        }

        UNUserNotificationCenter.current().delegate = self
        NotificationScheduler.shared.registerCategories()
        SubscriptionManager.shared.configure()

        // Widget data sync
        let struggles = AppState.shared.userProfile.struggles
        if !struggles.isEmpty {
            NudgeWidgetDataStore.sync(struggles: struggles)
        }

        // Mixpanelは常に初期化（ファーストパーティAnalytics、IDFAを使用しない）
        AnalyticsManager.shared.configure()
        let analyticsUserID = SubscriptionManager.shared.isConfigured ? Purchases.shared.appUserID : nil
        if let analyticsUserID { AnalyticsManager.shared.identify(userId: analyticsUserID) }

        // Singular SDK: Install attribution + SKAN 管理（ATT なし、IDFV + SKAN 運用）
        // Purchase は RevenueCat → Singular S2S で自動送信（アプリ側不要）
        SingularManager.shared.configure(launchOptions: launchOptions)

        // ASA Attribution取得 → app_opened トラック（この順序が重要）
        Task {
            await ASAAttributionManager.shared.fetchAttributionIfNeeded()
            AnalyticsManager.shared.track(.appOpened)
        }

        Task {
            // v1.8.7: affirmations are delivered REMOTELY (APNs) — no local scheduling.
            // Register for remote notifications on launch if already authorized so the
            // device token reaches the backend and recovers without extra user action.
            await registerForRemoteIfAuthorized()
            await SubscriptionManager.shared.refreshOfferings()
            await AuthHealthCheck.shared.warmBackend()
        }
        return true
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        AnalyticsManager.shared.resumeCurrentScreenVisit()
        // Distinct open days for post-value App Store review prompts.
        Task { @MainActor in
            ReviewPromptCoordinator.shared.recordAppOpen()
            DecisionPointRecorder.shared.recordAppOpened()
        }
        // Best-effort: recover APNs token registration if it was delayed on first run.
        Task { await registerForRemoteIfAuthorized() }
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        AnalyticsManager.shared.suspendCurrentScreenVisit()
    }

    /// Register for remote notifications when the user has granted alert authorization.
    /// Idempotent; iOS de-dupes. The resulting token is sent to the backend by
    /// `didRegisterForRemoteNotificationsWithDeviceToken`.
    private func registerForRemoteIfAuthorized() async {
        let authorized = await NotificationScheduler.shared.isAuthorizedForAlerts()
        if authorized {
            await MainActor.run { UIApplication.shared.registerForRemoteNotifications() }
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        let content = notification.request.content
        AnalyticsManager.shared.track(.notificationReceived, properties: [
            "notification_id": content.userInfo["messageId"] as? String ?? notification.request.identifier,
            "quote_id": content.userInfo["quoteId"] as? String ?? "unavailable",
            "app_state": "foreground",
        ])
        // Phase 1 decision-point record: foreground receipt = delivered.
        let deliveryId = content.userInfo["delivery_id"] as? String ?? content.userInfo["messageId"] as? String ?? notification.request.identifier
        let messageId = content.userInfo["quoteId"] as? String
        Task { @MainActor in
            DecisionPointRecorder.shared.recordNotificationAssignment(userInfo: content.userInfo, deliveryId: deliveryId)
            DecisionPointRecorder.shared.recordNotificationOutcome(
                deliveryId: deliveryId,
                messageId: messageId,
                outcome: "delivered",
                at: notification.date
            )
        }
        if #available(iOS 14.0, *) {
            completionHandler([.banner, .list, .sound])
        } else {
            completionHandler([.alert, .sound])
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        let content = response.notification.request.content
        let quoteID = content.userInfo["quoteId"] as? String
        let alertBody = content.body
        let isDismiss = response.actionIdentifier == UNNotificationDismissActionIdentifier ||
            response.actionIdentifier == NotificationScheduler.Action.dismissAll.rawValue
        let deliveryId = content.userInfo["delivery_id"] as? String ?? content.userInfo["messageId"] as? String ?? response.notification.request.identifier

        Task { @MainActor in
            DecisionPointRecorder.shared.recordNotificationAssignment(userInfo: content.userInfo, deliveryId: deliveryId)
            // The OS notification date is actual delivery evidence, including a
            // background notification opened after relaunch.
            DecisionPointRecorder.shared.recordNotificationOutcome(
                deliveryId: deliveryId, messageId: quoteID, outcome: "delivered", at: response.notification.date
            )
            DecisionPointRecorder.shared.recordNotificationOutcome(
                deliveryId: deliveryId,
                messageId: quoteID,
                outcome: isDismiss ? "skipped" : "opened"
            )
            if !isDismiss {
                DecisionPointRecorder.shared.recordResponse(deliveryId: deliveryId, event: .appOpened)
                AnalyticsManager.shared.track(.notificationOpened, properties: [
                    "quote_id": quoteID ?? "unavailable", "notification_id": deliveryId
                ])
                QuoteNavigationCoordinator.shared.request(quoteID: quoteID, alertBody: alertBody, deliveryId: deliveryId)
            }
            completionHandler()
        }
    }

    // MARK: - APNs registration

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        Task { await PushTokenService.shared.register(deviceToken: deviceToken) }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // v1.8.7: notifications are remote-only. On registration failure we simply mark
        // the token unregistered; there is no local-notification fallback by design.
        print("APNs registration failed: \(error)")
        Task { @MainActor in
            AnalyticsManager.shared.track(.notificationRegistrationResult, properties: [
                "result": "failed",
                "source": "apns",
                "error_code": String((error as NSError).code),
            ])
            PushTokenService.shared.markUnregistered()
        }
    }
}
