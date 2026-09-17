// OnboardingV2Tests.swift
// Tests for onboarding v2: new OnboardingStep enum, PaywallStep, progress bar, migration

import XCTest
@testable import aniccaios

final class OnboardingV2Tests: XCTestCase {

    // MARK: - OnboardingStep Raw Values (v2)

    func test_welcome_rawValue_is0() {
        XCTAssertEqual(OnboardingStep.welcome.rawValue, 0)
    }

    func test_struggles_rawValue_is1() {
        XCTAssertEqual(OnboardingStep.struggles.rawValue, 1)
    }

    func test_struggleDepth_rawValue_is2() {
        XCTAssertEqual(OnboardingStep.struggleDepth.rawValue, 2)
    }

    func test_goals_rawValue_is3() {
        XCTAssertEqual(OnboardingStep.goals.rawValue, 3)
    }

    func test_personalizedInsight_rawValue_is4() {
        XCTAssertEqual(OnboardingStep.personalizedInsight.rawValue, 4)
    }

    func test_valueProp_rawValue_is5() {
        XCTAssertEqual(OnboardingStep.valueProp.rawValue, 5)
    }

    func test_liveDemo_rawValue_is6() {
        XCTAssertEqual(OnboardingStep.liveDemo.rawValue, 6)
    }

    func test_notifications_rawValue_is7() {
        XCTAssertEqual(OnboardingStep.notifications.rawValue, 7)
    }

    func test_allCases_count_is8() {
        XCTAssertEqual(OnboardingStep.allCases.count, 8)
    }

    // MARK: - PaywallStep Raw Values

    func test_paywallPrimer_rawValue_is0() {
        XCTAssertEqual(PaywallStep.primer.rawValue, 0)
    }

    func test_paywallTimeline_rawValue_is1() {
        XCTAssertEqual(PaywallStep.timeline.rawValue, 1)
    }

    func test_paywallPlanSelection_rawValue_is2() {
        XCTAssertEqual(PaywallStep.planSelection.rawValue, 2)
    }

    // MARK: - Progress Bar Calculation

    func test_progressBar_welcome_starts_at_20_percent() {
        let progress = OnboardingProgressBar.progress(for: .welcome)
        XCTAssertEqual(progress, 0.2, accuracy: 0.001)
    }

    func test_progressBar_notifications_is_100_percent() {
        let progress = OnboardingProgressBar.progress(for: .notifications)
        XCTAssertEqual(progress, 1.0, accuracy: 0.001)
    }

    func test_progressBar_struggles_correct() {
        // 0.2 + 0.8 * (1/7) = 0.2 + 0.1143 = 0.3143
        let progress = OnboardingProgressBar.progress(for: .struggles)
        let expected = 0.2 + 0.8 * (1.0 / 7.0)
        XCTAssertEqual(progress, expected, accuracy: 0.001)
    }

    func test_progressBar_valueProp_correct() {
        // 0.2 + 0.8 * (5/7)
        let progress = OnboardingProgressBar.progress(for: .valueProp)
        let expected = 0.2 + 0.8 * (5.0 / 7.0)
        XCTAssertEqual(progress, expected, accuracy: 0.001)
    }

    // MARK: - v2 Migration (v1.6.1 rawValues → v2 rawValues)

    func test_v2Migration_old0_welcome_maps_to_welcome() {
        // Old rawValue 0 (welcome) → New 0 (welcome)
        XCTAssertEqual(OnboardingStep.migratedFromV1RawValue(0), .welcome)
    }

    func test_v2Migration_old1_struggles_maps_to_struggles() {
        // Old rawValue 1 (struggles) → New 1 (struggles)
        XCTAssertEqual(OnboardingStep.migratedFromV1RawValue(1), .struggles)
    }

    func test_v2Migration_old2_liveDemo_maps_to_liveDemo() {
        // Old rawValue 2 (liveDemo) → New 6 (liveDemo)
        XCTAssertEqual(OnboardingStep.migratedFromV1RawValue(2), .liveDemo)
    }

    func test_v2Migration_old3_notifications_maps_to_notifications() {
        // Old rawValue 3 (notifications) → New 7 (notifications)
        XCTAssertEqual(OnboardingStep.migratedFromV1RawValue(3), .notifications)
    }

    func test_v2Migration_unknown_maps_to_welcome() {
        XCTAssertEqual(OnboardingStep.migratedFromV1RawValue(99), .welcome)
    }

    // MARK: - UserProfile goals and struggleFrequency

    func test_userProfile_goals_defaults_to_empty() {
        let profile = UserProfile()
        XCTAssertTrue(profile.goals.isEmpty)
    }

    func test_userProfile_struggleFrequency_defaults_to_nil() {
        let profile = UserProfile()
        XCTAssertNil(profile.struggleFrequency)
    }

    func test_userProfile_goals_roundtrip_encoding() throws {
        var profile = UserProfile()
        profile.goals = ["better_sleep", "emotional_calm", "inner_peace"]
        profile.struggleFrequency = "daily"

        let data = try JSONEncoder().encode(profile)
        let decoded = try JSONDecoder().decode(UserProfile.self, from: data)

        XCTAssertEqual(decoded.goals, ["better_sleep", "emotional_calm", "inner_peace"])
        XCTAssertEqual(decoded.struggleFrequency, "daily")
    }

    // MARK: - Analytics Events

    func test_analytics_onboardingStruggleDepthCompleted_exists() {
        let event = AnalyticsEvent.onboardingStruggleDepthCompleted
        XCTAssertEqual(event.rawValue, "onboarding_struggle_depth_completed")
    }

    func test_analytics_onboardingGoalsCompleted_exists() {
        let event = AnalyticsEvent.onboardingGoalsCompleted
        XCTAssertEqual(event.rawValue, "onboarding_goals_completed")
    }

    func test_analytics_onboardingInsightCompleted_exists() {
        let event = AnalyticsEvent.onboardingInsightCompleted
        XCTAssertEqual(event.rawValue, "onboarding_insight_completed")
    }

    func test_analytics_onboardingValuePropCompleted_exists() {
        let event = AnalyticsEvent.onboardingValuePropCompleted
        XCTAssertEqual(event.rawValue, "onboarding_valueprop_completed")
    }

    func test_analytics_paywallPrimerViewed_exists() {
        let event = AnalyticsEvent.paywallPrimerViewed
        XCTAssertEqual(event.rawValue, "paywall_primer_viewed")
    }

    func test_analytics_paywallTimelineViewed_exists() {
        let event = AnalyticsEvent.paywallTimelineViewed
        XCTAssertEqual(event.rawValue, "paywall_timeline_viewed")
    }

    func test_analytics_paywallPlanSelectionViewed_exists() {
        let event = AnalyticsEvent.paywallPlanSelectionViewed
        XCTAssertEqual(event.rawValue, "paywall_plan_selection_viewed")
    }

    func test_analytics_paywallDrawerViewed_exists() {
        let event = AnalyticsEvent.paywallDrawerViewed
        XCTAssertEqual(event.rawValue, "paywall_drawer_viewed")
    }

    func test_analytics_paywallDrawerConverted_exists() {
        let event = AnalyticsEvent.paywallDrawerConverted
        XCTAssertEqual(event.rawValue, "paywall_drawer_converted")
    }
}
