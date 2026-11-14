import Foundation
import SwiftUI
import Mixpanel
import StoreKit
import OSLog
import RevenueCat

/// アプリ全体のアナリティクスを管理するシングルトン
/// Jake Mor's Tip #1: "Most important metric is App Install → Paywall View"
@MainActor
final class AnalyticsManager {
    static let shared = AnalyticsManager()
    private let logger = Logger(subsystem: "com.anicca.ios", category: "Analytics")
    private let purchaseObservations = PurchaseObservationLedger()
    private var sessionID: String { screenVisits.sessionID }
    private var screenVisits = ScreenVisitLedger()

    private var context: [String: MixpanelType] {
        #if targetEnvironment(simulator)
        let environment = "simulator"
        #else
        let environment = Bundle.main.appStoreReceiptURL?.lastPathComponent == "sandboxReceipt" ? "sandbox" : "production"
        #endif
        var values: [String: MixpanelType] = [
            "app_id": "ai.anicca.app.ios",
            "app_version": AppConfig.appVersion,
            "app_build": Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown",
            "app_environment": environment,
            "flow_version": "adaptive-onboarding-v2",
            "session_id": sessionID,
            "language": AppState.shared.effectiveLanguage.rawValue,
            "locale": Locale.current.identifier,
            "device_region_code": Locale.current.region?.identifier ?? "unknown",
            "storefront_country_code": AppState.shared.currentStorefrontCountryCode ?? "unknown",
        ]
        return values
    }
    
    private init() {}
    
    // MARK: - Configuration
    
    func configure() {
        let token = AppConfig.mixpanelToken
        // trackAutomaticEvents: false (公式推奨 - クライアントサイドの自動イベントは信頼性が低い)
        Mixpanel.initialize(token: token, trackAutomaticEvents: false)
        
        // イベントpayloadを端末ログへ出力しない。
        Mixpanel.mainInstance().loggingEnabled = false
        
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
        screenVisits.resetSession()
        logger.info("Mixpanel reset")
    }
    
    // MARK: - Event Tracking
    
    /// 汎用イベントトラッキング
    func track(_ event: AnalyticsEvent, properties: [String: MixpanelType]? = nil) {
        var merged = properties ?? [:]
        merged.merge(context) { _, contextValue in contextValue }
        merged["event_id"] = UUID().uuidString
        merged["event_timestamp"] = Int(Date().timeIntervalSince1970 * 1_000)
        Mixpanel.mainInstance().track(event: event.rawValue, properties: merged)
        logger.debug("Tracked event: \(event.rawValue, privacy: .public)")
    }

    func trackScreenViewed(screenID: AnalyticsScreenID, flowID: String, screenInstanceID: String = UUID().uuidString) {
        let enteredAt = Date()
        let entry = screenVisits.enter(
            screenID: screenID.rawValue,
            screenInstanceID: screenInstanceID,
            flowID: flowID,
            at: enteredAt
        )
        guard case .entered(let previousExit) = entry else { return }
        if let previousExit { trackScreenExit(previousExit) }

        recordScreenView(screenID: screenID.rawValue, flowID: flowID, screenInstanceID: screenInstanceID)
    }

    private func recordScreenView(screenID: String, flowID: String, screenInstanceID: String) {
        let properties: [String: MixpanelType] = [
            "screen_id": screenID,
            "screen_instance_id": screenInstanceID,
            "flow_id": flowID,
            "flow_version": "adaptive-onboarding-v2",
        ]
        track(.screenViewed, properties: properties)
        if screenID == AnalyticsScreenID.paywall.rawValue {
            track(.paywallShown, properties: properties)
            updateSKANConversionValue(2)
        }
    }

    func trackScreenViewedIfNeeded(screenID: AnalyticsScreenID, flowID: String) {
        guard screenVisits.currentVisit?.screenID != screenID.rawValue
                || screenVisits.currentVisit?.flowID != flowID else { return }
        trackScreenViewed(screenID: screenID, flowID: flowID)
    }

    func trackScreenExited(nextScreenID: String, screenInstanceID: String? = nil) {
        guard let exit = screenVisits.exit(
            nextScreenID: nextScreenID,
            screenInstanceID: screenInstanceID,
            at: Date()
        ) else { return }
        trackScreenExit(exit)
    }

    private func trackScreenExit(_ exit: ScreenVisitLedger.Exit) {
        track(.screenExited, properties: [
            "screen_id": exit.screenID,
            "screen_instance_id": exit.screenInstanceID,
            "flow_id": exit.flowID,
            "next_screen_id": exit.nextScreenID,
            "observed_duration_ms": exit.observedDurationMS,
        ])
    }

    /// Backgrounding is not a user exit; keep the screen so foreground can start a fresh visit.
    func suspendCurrentScreenVisit() {
        screenVisits.suspend()
    }

    func resumeCurrentScreenVisit() {
        guard let visit = screenVisits.resume(at: Date(), screenInstanceID: UUID().uuidString) else { return }
        recordScreenView(screenID: visit.screenID, flowID: visit.flowID, screenInstanceID: visit.screenInstanceID)
    }

    // MARK: - Convenience Methods

    /// トライアル開始
    func trackTrialStarted(productId: String, flowID: String) {
        track(.trialStarted, properties: [
            "product_id": productId,
            "flow_id": flowID,
        ])
    }

    /// 購入開始。product_id だけでは分析側で「どのプランのカードが押されたか」を
    /// 即座に読めなかった (2026-11-10 ファネル分析の計装欠陥) ため、パッケージ・
    /// プラン種別・オファリング・トライアル有無を明示プロパティとして併記する。
    func trackPurchaseStarted(package: Package, offeringID: String?, flowID: String) {
        track(.purchaseStarted, properties: [
            "product_id": package.storeProduct.productIdentifier,
            "package_id": package.identifier,
            "plan_name": Self.planName(for: package.packageType),
            "offering_id": offeringID ?? "unknown",
            "has_trial": package.storeProduct.introductoryDiscount != nil,
            "flow_id": flowID,
        ])
    }

    /// プラン種別を分析で読める安定した文字列にする。
    static func planName(for packageType: PackageType) -> String {
        switch packageType {
        case .annual: return "annual"
        case .monthly: return "monthly"
        case .weekly: return "weekly"
        case .lifetime: return "lifetime"
        case .sixMonth: return "six_month"
        case .threeMonth: return "three_month"
        case .twoMonth: return "two_month"
        case .custom: return "custom"
        default: return "unknown"
        }
    }

    /// RevenueCat Experiment の露出。割当 Offering が確定し、そのゲートで
    /// ペイウォールが実際に表示された時点で1回だけ発火する。
    /// これまで AnalyticsEvent に対応する送信呼び出しが存在せず、
    /// HARD-PAYWALL-20261108 の A/B 判定が Mixpanel 側で不能だった。
    func trackExperimentExposure(offeringIdentifier: String?, gateVariant: PaywallGateVariant, flowID: String) {
        track(.experimentExposure, properties: [
            "experiment_id": PaywallGateVariant.experimentIdentifier,
            "variant": gateVariant.rawValue,
            "offering_id": offeringIdentifier ?? "unknown",
            "paywall_gate_variant": gateVariant.rawValue,
            "flow_id": flowID,
        ])
        Purchases.shared.trackCustomPaywallImpression()
    }

    func trackPurchaseResult(_ result: String, productID: String, flowID: String, errorCode: String? = nil) {
        var properties: [String: MixpanelType] = [
            "product_id": productID,
            "result": result,
            "flow_id": flowID,
        ]
        if let errorCode { properties["error_code"] = errorCode }
        track(.purchaseResult, properties: properties)
    }

    func trackRestoreStarted(source: String, flowID: String) {
        track(.restoreStarted, properties: ["source": source, "flow_id": flowID])
    }

    func trackRestoreResult(_ result: String, source: String, flowID: String, errorCode: String? = nil) {
        var properties: [String: MixpanelType] = ["result": result, "flow_id": flowID]
        properties["source"] = source
        if let errorCode { properties["error_code"] = errorCode }
        track(.restoreResult, properties: properties)
    }
    
    /// 購入完了
    func observePurchase(package: Package, transaction: StoreTransaction?, customerInfo: CustomerInfo, flowID: String) {
        guard purchaseObservations.record(transaction?.transactionIdentifier) else { return }
        let entitlement = customerInfo.entitlements[AppConfig.revenueCatEntitlementId]
        let isTrial = entitlement?.isActive == true && entitlement?.periodType == .trial
        var properties: [String: MixpanelType] = [
            "product_id": package.storeProduct.productIdentifier,
            "result": "success",
            "entitlement_state": isTrial ? "trial" : (entitlement?.isActive == true ? "active" : "unknown"),
            "flow_id": flowID,
        ]
        if let currency = package.storeProduct.currencyCode { properties["currency"] = currency }

        track(.purchaseResult, properties: properties)
        if flowID == "onboarding" || flowID == "legacy_paywall" {
            track(.onboardingPaywallPurchased, properties: ["flow_id": flowID])
        }
        if isTrial { trackTrialStarted(productId: package.storeProduct.productIdentifier, flowID: flowID) }
        // Actual amounts/renewals/refunds are reconciled from RevenueCat and Apple.
        updateSKANConversionValue(3)
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
    case screenViewed = "screen_viewed"
    case screenExited = "screen_exited"
    case firstAffirmationViewed = "first_affirmation_viewed"
    case personalizationApplied = "personalization_applied"
    case affirmationViewed = "affirmation_viewed"
    case affirmationLiked = "affirmation_liked"
    case affirmationUnliked = "affirmation_unliked"
    case affirmationShared = "affirmation_shared"
    case notificationOpened = "notification_opened"
    case notificationReceived = "notification_received"
    case notificationRegistrationResult = "notification_registration_result"
    case notificationDestinationResolved = "notification_destination_resolved"
    case notificationPermissionRequested = "notification_permission_requested"
    case notificationPermissionResult = "notification_permission_result"
    case notificationPrimingViewed = "notification_priming_viewed"
    case nudgeDecisionMade = "nudge_decision_made"
    case purchaseStarted = "purchase_started"
    case purchaseResult = "purchase_result"
    case restoreStarted = "restore_started"
    case restoreResult = "restore_result"
    case experimentExposure = "experiment_exposure"
    case productSelected = "product_selected"
    // App
    case appOpened = "app_opened"

    // Onboarding funnel (v3 — spec-185 Bible-compliant 20-step)
    case onboardingStarted = "onboarding_started"
    case onboardingStepCompleted = "onboarding_step_completed"
    case onboardingStepViewed = "onboarding_step_viewed"
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
    case paywallShown = "paywall_shown"
    case paywallPrimerViewed = "paywall_primer_viewed"
    case paywallPlanSelectionViewed = "paywall_plan_selection_viewed"
    case onboardingPaywallCustomerInfoResult = "onboarding_paywall_customer_info_result"
    case onboardingPaywallOfferingLoadResult = "onboarding_paywall_offering_load_result"
    case onboardingPaywallPurchased = "onboarding_paywall_purchased"
    case onboardingPaywallDismissedFree = "onboarding_paywall_dismissed_free"

    // Subscription
    case trialStarted = "trial_started"
    case trialCancelled = "trial_cancelled"
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

enum AnalyticsScreenID: String, CaseIterable {
    case onboardingWelcome = "onboarding.welcome"
    case onboardingGoal = "onboarding.goal"
    case onboardingName = "onboarding.name"
    case onboardingBirthContext = "onboarding.birth_context"
    case onboardingMoodBaseline = "onboarding.mood_baseline"
    case onboardingBeliefThemes = "onboarding.belief_themes"
    case onboardingTone = "onboarding.tone"
    case onboardingLifeContext = "onboarding.life_context"
    case onboardingRoutineAnchors = "onboarding.routine_anchors"
    case onboardingPriorAttempts = "onboarding.prior_attempts"
    case onboardingStartReason = "onboarding.start_reason"
    case onboardingQuietHours = "onboarding.quiet_hours"
    case onboardingStressTrigger = "onboarding.stress_trigger"
    case onboardingAnxietyTarget = "onboarding.anxiety_target"
    case onboardingSelfCriticism = "onboarding.self_criticism"
    case onboardingAvoidanceTask = "onboarding.avoidance_task"
    case onboardingSleepReason = "onboarding.sleep_reason"
    case onboardingBedtime = "onboarding.bedtime"
    case onboardingWakeTime = "onboarding.wake_time"
    case onboardingPriorHelpfulness = "onboarding.prior_helpfulness"
    case onboardingPainPoints = "onboarding.pain_points"
    case onboardingStruggleFrequency = "onboarding.struggle_frequency"
    case onboardingReminderSchedule = "onboarding.reminder_schedule"
    case onboardingProcessing = "onboarding.processing"
    case onboardingFirstAffirmation = "onboarding.first_affirmation"
    case onboardingComparison = "onboarding.comparison"
    case onboardingNotifications = "onboarding.notifications"
    case paywall = "paywall"
    case retentionOffer = "paywall.retention_offer"
    case feed = "feed"
    case feedCollections = "feed.collections"
    case feedSaved = "feed.saved"
    case feedReminders = "feed.reminders"
    case feedThemes = "feed.themes"
    case feedSettings = "feed.settings"
    case settingsSubscription = "settings.subscription"

    static func onboarding(_ step: OnboardingStep) -> AnalyticsScreenID {
        switch step {
        case .welcome: return .onboardingWelcome
        case .goal: return .onboardingGoal
        case .name: return .onboardingName
        case .birthContext: return .onboardingBirthContext
        case .moodBaseline: return .onboardingMoodBaseline
        case .beliefThemes: return .onboardingBeliefThemes
        case .tone: return .onboardingTone
        case .lifeContext: return .onboardingLifeContext
        case .routineAnchors: return .onboardingRoutineAnchors
        case .priorAttempts: return .onboardingPriorAttempts
        case .startReason: return .onboardingStartReason
        case .quietHours: return .onboardingQuietHours
        case .stressTrigger: return .onboardingStressTrigger
        case .anxietyTarget: return .onboardingAnxietyTarget
        case .selfCriticism: return .onboardingSelfCriticism
        case .avoidanceTask: return .onboardingAvoidanceTask
        case .sleepReason: return .onboardingSleepReason
        case .bedtime: return .onboardingBedtime
        case .wakeTime: return .onboardingWakeTime
        case .priorHelpfulness: return .onboardingPriorHelpfulness
        case .painPoints: return .onboardingPainPoints
        case .struggleFreq: return .onboardingStruggleFrequency
        case .nudgeTimes: return .onboardingReminderSchedule
        case .processing: return .onboardingProcessing
        case .planReveal: return .onboardingFirstAffirmation
        case .comparison: return .onboardingComparison
        case .notifications: return .onboardingNotifications
        }
    }
}

private struct AnalyticsScreenModifier: ViewModifier {
    let screenID: AnalyticsScreenID
    let flowID: String

    func body(content: Content) -> some View {
        content.onAppear {
            AnalyticsManager.shared.trackScreenViewedIfNeeded(screenID: screenID, flowID: flowID)
        }
    }
}

extension View {
    func analyticsScreen(_ screenID: AnalyticsScreenID, flowID: String) -> some View {
        modifier(AnalyticsScreenModifier(screenID: screenID, flowID: flowID))
    }
}
