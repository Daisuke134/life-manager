// v1.8.2 — Singular SDK 再統合 + RevenueCat→Singular→TikTok SAN
import UIKit
import UserNotifications
import OSLog
import BackgroundTasks
import PostHog
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

        // PostHog: A/B テスト + Session Replay（RevenueCat configure の後）。
        // The project-specific key and host are supplied by ignored xcconfig files.
        if let postHogKey = Bundle.main.object(forInfoDictionaryKey: "POSTHOG_API_KEY") as? String,
           let postHogHost = Bundle.main.object(forInfoDictionaryKey: "POSTHOG_HOST") as? String,
           !postHogKey.isEmpty, !postHogHost.isEmpty {
            let phConfig = PostHogConfig(apiKey: postHogKey, host: postHogHost)
            phConfig.sessionReplay = true
            phConfig.sessionReplayConfig.maskAllTextInputs = true
            phConfig.sessionReplayConfig.maskAllImages = false
            PostHogSDK.shared.setup(phConfig)
            PostHogSDK.shared.identify(Purchases.shared.appUserID)
            // identify() 後にフラグを明示リロード（ユーザーコンテキスト変更でpreload分が無効になるため）
            // completion callback で featureFlagsReady を立てる → Paywall が nil を読まない
            PostHogSDK.shared.reloadFeatureFlags {
                Task { @MainActor in
                    AppState.shared.featureFlagsReady = true
                }
            }
        } else {
            print("[PostHog] private build configuration is missing; skipping setup")
        }

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
        // Best-effort: recover APNs token registration if it was delayed on first run.
        Task { await registerForRemoteIfAuthorized() }
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
        if #available(iOS 14.0, *) {
            completionHandler([.banner, .list, .sound])
        } else {
            completionHandler([.alert, .sound])
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        defer { completionHandler() }

        let userInfo = response.notification.request.content.userInfo

        // v1.8.7: Affirmation quote tap (remote APNs) → scroll Feed to that quote.
        // If quoteId is missing/unknown the Feed simply opens at the top (graceful).
        if let quoteId = userInfo["quoteId"] as? String, !quoteId.isEmpty {
            NotificationCenter.default.post(
                name: .aniccaScrollToQuote,
                object: nil,
                userInfo: ["quoteId": quoteId]
            )
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
            PushTokenService.shared.markUnregistered()
        }
    }
}
