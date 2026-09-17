import Foundation
import Mixpanel
import PostHog
import StoreKit
import OSLog

/// アプリ全体のアナリティクスを管理するシングルトン
/// Jake Mor's Tip #1: "Most important metric is App Install → Paywall View"
@MainActor
final class AnalyticsManager {
    static let shared = AnalyticsManager()
    private let logger = Logger(subsystem: "com.anicca.ios", category: "Analytics")
    
    private init() {}
    
    // MARK: - Configuration
    
    func configure() {
        let token = AppConfig.mixpanelToken
        // trackAutomaticEvents: false (公式推奨 - クライアントサイドの自動イベントは信頼性が低い)
        Mixpanel.initialize(token: token, trackAutomaticEvents: false)
        
        // ログを常時有効化（Debug/Release両方でイベント送信を確認可能）
        Mixpanel.mainInstance().loggingEnabled = true
        
        logger.info("Mixpanel initialized")
    }
    
    /// ユーザーIDを設定（ログイン時に呼び出し）
    func identify(userId: String) {
        Mixpanel.mainInstance().identify(distinctId: userId)
        logger.info("Mixpanel identified user: \(userId, privacy: .private(mask: .hash))")
    }
    
    /// ユーザープロファイル情報を設定
    func setUserProperties(_ properties: [String: MixpanelType]) {
        Mixpanel.mainInstance().people.set(properties: properties)
    }
    
    /// 単一のユーザープロパティを設定
    /// - Parameters:
    ///   - key: プロパティキー（例: "acquisition_source", "gender"）
    ///   - value: プロパティ値
    func setUserProperty(_ key: String, value: MixpanelType) {
        Mixpanel.mainInstance().people.set(properties: [key: value])
        logger.debug("Set user property: \(key, privacy: .public)")
    }
    
    /// ログアウト時にリセット
    func reset() {
        Mixpanel.mainInstance().reset()
        logger.info("Mixpanel reset")
    }
    
    // MARK: - Event Tracking
    
    /// 汎用イベントトラッキング
    func track(_ event: AnalyticsEvent, properties: [String: MixpanelType]? = nil) {
        Mixpanel.mainInstance().track(event: event.rawValue, properties: properties)
        logger.debug("Tracked event: \(event.rawValue, privacy: .public)")
    }
    
    /// PostHog event tracking (A/B test layer — runs alongside Mixpanel)
    func trackPostHog(_ eventName: String, properties: [String: Any]? = nil) {
        PostHogSDK.shared.capture(eventName, properties: properties)
        logger.debug("PostHog captured: \(eventName, privacy: .public)")
    }

    // MARK: - Convenience Methods

    /// トライアル開始
    func trackTrialStarted(productId: String) {
        track(.trialStarted, properties: [
            "product_id": productId
        ])
    }
    
    /// 購入完了
    func trackPurchaseCompleted(productId: String, revenue: Double) {
        track(.purchaseCompleted, properties: [
            "product_id": productId,
            "revenue": revenue
        ])
        
        // Revenue tracking
        Mixpanel.mainInstance().people.trackCharge(amount: revenue)

        // Purchase は RevenueCat → Singular → TikTok SAN で自動送信（二重カウント防止）
        updateSKANConversionValue(3)
    }

    /// ペイウォール表示
    func trackPaywallViewed() {
        track(.paywallPlanSelectionViewed)
        updateSKANConversionValue(2)
    }

    /// SKAdNetwork conversion value 更新
    func updateSKANConversionValue(_ value: Int) {
        if #available(iOS 16.1, *) {
            let coarse: SKAdNetwork.CoarseConversionValue = value >= 3 ? .high : value >= 1 ? .medium : .low
            SKAdNetwork.updatePostbackConversionValue(value, coarseValue: coarse) { error in
                if let error { self.logger.error("SKAN update failed: \(error.localizedDescription)") }
            }
        } else if #available(iOS 15.4, *) {
            SKAdNetwork.updatePostbackConversionValue(value) { error in
                if let error { self.logger.error("SKAN update failed: \(error.localizedDescription)") }
            }
        }
        logger.debug("SKAN conversion value updated: \(value)")
    }
    
    /// 音声セッション開始
    func trackSessionStarted(habitType: String, customHabitId: String? = nil) {
        var props: [String: MixpanelType] = ["habit_type": habitType]
        if let customId = customHabitId {
            props["custom_habit_id"] = customId
        }
        track(.sessionStarted, properties: props)
    }
    
    /// 音声セッション完了
    func trackSessionCompleted(habitType: String, durationSeconds: Int) {
        track(.sessionCompleted, properties: [
            "habit_type": habitType,
            "duration_seconds": durationSeconds
        ])
    }
}

// MARK: - Analytics Events

enum AnalyticsEvent: String {
    // App
    case appOpened = "app_opened"

    // Onboarding funnel (v3 — spec-185 Bible-compliant 20-step)
    case onboardingStarted = "onboarding_started"
    case onboardingWelcomeCompleted = "onboarding_welcome_completed"
    case onboardingStrugglesCompleted = "onboarding_struggles_completed"
    case onboardingStruggleDepthCompleted = "onboarding_struggle_depth_completed"
    case onboardingGoalsCompleted = "onboarding_goals_completed"
    case onboardingInsightCompleted = "onboarding_insight_completed"
    case onboardingValuePropCompleted = "onboarding_valueprop_completed"
    case onboardingNotificationsCompleted = "onboarding_notifications_completed"
    case onboardingCompleted = "onboarding_completed"
    case onboardingStepAdvanced = "onboarding_step_advanced"
    case onboardingStepBack = "onboarding_step_back"
    case tinderPainCardAgreed = "tinder_pain_card_agreed"
    case tinderPainCardDismissed = "tinder_pain_card_dismissed"
    case shareCompleted = "share_completed"
    case ratingPromptShown = "rating_prompt_shown"
    case ratingPromptYesTapped = "rating_prompt_yes_tapped"
    case ratingPromptNoTapped = "rating_prompt_no_tapped"
    case ratingStoreReviewRequested = "rating_store_review_requested"
    case feedbackFormSubmitted = "feedback_form_submitted"
    case feedbackFormSkipped = "feedback_form_skipped"

    // Paywall funnel
    case paywallPrimerViewed = "paywall_primer_viewed"
    case paywallPlanSelectionViewed = "paywall_plan_selection_viewed"
    case onboardingPaywallPurchased = "onboarding_paywall_purchased"
    case onboardingPaywallDismissedFree = "onboarding_paywall_dismissed_free"

    // Subscription
    case trialStarted = "trial_started"
    case trialCancelled = "trial_cancelled"
    case purchaseCompleted = "purchase_completed"
    case subscriptionRenewed = "subscription_renewed"
    case subscriptionCancelled = "subscription_cancelled"

    // Voice Session
    case sessionStarted = "session_started"
    case sessionCompleted = "session_completed"
    case sessionFailed = "session_failed"

    // Habits
    case habitCreated = "habit_created"
    case habitDeleted = "habit_deleted"
    case habitNotificationTapped = "habit_notification_tapped"

    // Engagement
    case talkTabOpened = "talk_tab_opened"
    case settingsOpened = "settings_opened"

    // Nudge
    case nudgeTapped = "nudge_tapped"
    case nudgeIgnored = "nudge_ignored"
    case nudgePositiveFeedback = "nudge_positive_feedback"
    case nudgeNegativeFeedback = "nudge_negative_feedback"
    case nudgeScheduled = "nudge_scheduled"
}

