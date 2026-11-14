// OnboardingV2Tests.swift
// Tests for onboarding v2: new OnboardingStep enum, PaywallStep, progress bar, migration

import XCTest
@testable import aniccaios

@MainActor
final class OnboardingV2Tests: XCTestCase {

    func test_persistedStepRawValues_areStable() {
        XCTAssertEqual(OnboardingStep.welcome.rawValue, 0)
        XCTAssertEqual(OnboardingStep.goal.rawValue, 1)
        XCTAssertEqual(OnboardingStep.painPoints.rawValue, 2)
        XCTAssertEqual(OnboardingStep.struggleFreq.rawValue, 3)
        XCTAssertEqual(OnboardingStep.nudgeTimes.rawValue, 4)
        XCTAssertEqual(OnboardingStep.processing.rawValue, 5)
        XCTAssertEqual(OnboardingStep.planReveal.rawValue, 6)
        XCTAssertEqual(OnboardingStep.comparison.rawValue, 7)
        XCTAssertEqual(OnboardingStep.notifications.rawValue, 8)
        XCTAssertEqual(OnboardingStep.name.rawValue, 9)
    }

    func test_initialJourney_asksDeviceOnlyNameSeparatelyAfterGoal() {
        XCTAssertEqual(OnboardingStep.initialJourney, [
            .welcome, .goal, .name, .birthContext, .moodBaseline, .painPoints, .struggleFreq,
            .beliefThemes, .tone, .lifeContext, .routineAnchors, .priorAttempts, .startReason, .quietHours,
            .planReveal, .nudgeTimes, .notifications
        ])
        XCTAssertEqual(OnboardingStep.welcome.nextInitialStep, .goal)
        XCTAssertEqual(OnboardingStep.goal.nextInitialStep, .name)
        XCTAssertEqual(OnboardingStep.name.nextInitialStep, .birthContext)
        XCTAssertEqual(OnboardingStep(rawValue: 9)?.resumableStep(painPointIds: []), .name)
        XCTAssertEqual(AnalyticsScreenID.onboarding(.name).rawValue, "onboarding.name")
        XCTAssertEqual(AnalyticsScreenID.onboarding(.birthContext).rawValue, "onboarding.birth_context")
        XCTAssertNil(OnboardingStep.notifications.nextInitialStep)
    }

    func test_resumingWelcome_keepsIntroduction() {
        XCTAssertEqual(OnboardingStep.welcome.resumableInitialStep, .welcome)
    }

    func test_retiredSteps_resumeAtPreview() {
        XCTAssertEqual(OnboardingStep.processing.resumableInitialStep, .planReveal)
        XCTAssertEqual(OnboardingStep.comparison.resumableInitialStep, .planReveal)
    }

    func test_progressBar_followsJourneyOrderNotRawValues() {
        for (index, step) in OnboardingStep.initialJourney.enumerated() {
            XCTAssertEqual(OnboardingProgressBar.progress(for: step), Double(index + 1) / 17, accuracy: 0.001)
        }
    }

    func test_v7Migration_preservesQuestionStateAndSkipsRating() {
        XCTAssertEqual(OnboardingStep.migratedFromV7RawValue(0), .welcome)
        XCTAssertEqual(OnboardingStep.migratedFromV7RawValue(1), .goal)
        XCTAssertEqual(OnboardingStep.migratedFromV7RawValue(8), .notifications)
        XCTAssertEqual(OnboardingStep.migratedFromV7RawValue(9), .notifications)
        XCTAssertNil(OnboardingStep.migratedFromV7RawValue(99))
    }

    func test_v6Migration_retiredScreensResolveToReachableSteps() {
        for rawValue in 0...18 {
            let migrated = OnboardingStep.migratedFromV6RawValue(rawValue)
            XCTAssertNotNil(migrated)
            if let migrated {
                XCTAssertTrue(OnboardingStep.initialJourney.contains(migrated.resumableInitialStep))
            }
        }
        XCTAssertNil(OnboardingStep.migratedFromV6RawValue(99))
    }

    func test_paywallStepRawValues_areStable() {
        XCTAssertEqual(PaywallStep.primer.rawValue, 0)
        XCTAssertEqual(PaywallStep.planSelection.rawValue, 1)
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

    func test_analytics_paywallPlanSelectionViewed_exists() {
        let event = AnalyticsEvent.paywallPlanSelectionViewed
        XCTAssertEqual(event.rawValue, "paywall_plan_selection_viewed")
    }

    // MARK: - PaywallGateVariant (2026-11-08 hard paywall A/B)

    func test_gateVariant_oldHardOffering_resolvesSoft() {
        XCTAssertEqual(
            PaywallGateVariant.resolve(offeringIdentifier: "anicca_variant_b_hard"),
            .soft
        )
    }

    func test_gateVariant_controlOffering_resolvesSoft() {
        XCTAssertEqual(
            PaywallGateVariant.resolve(offeringIdentifier: "anicca_variant_b"),
            .soft
        )
    }

    func test_gateVariant_missingOrLegacyOffering_resolvesSoft() {
        XCTAssertEqual(PaywallGateVariant.resolve(offeringIdentifier: nil), .soft)
        XCTAssertEqual(PaywallGateVariant.resolve(offeringIdentifier: "default"), .soft)
    }

    func test_gateVariant_closeButton_onboardingHard_isShown() {
        XCTAssertTrue(PaywallGateVariant.showsCloseButton(flowID: "onboarding", variant: .hard))
    }

    func test_gateVariant_closeButton_onboardingSoft_isShown() {
        XCTAssertTrue(PaywallGateVariant.showsCloseButton(flowID: "onboarding", variant: .soft))
    }

    func test_gateVariant_closeButton_settingsHard_isShown() {
        XCTAssertTrue(PaywallGateVariant.showsCloseButton(flowID: "settings_subscription", variant: .hard))
    }

    func test_theme_access_freeHasTwoChoices_andProHasEveryTheme() {
        XCTAssertEqual(Set(ThemeID.allCases.filter { $0.isFree }), Set([.sageMist, .sandWave]))
        for theme in ThemeID.allCases {
            XCTAssertTrue(theme.isAvailable(isEntitled: true))
            XCTAssertEqual(theme.isAvailable(isEntitled: false), theme.isFree)
        }
    }

    // MARK: - PaywallOfferingSelection experiment priority (2026-11-08)

    private func resolveOffering(current: String?, all: [String: String]) -> String? {
        PaywallOfferingSelection.resolve(
            current: current,
            all: all,
            fallbackIdentifier: "anicca_variant_b",
            isUsableForAnicca: { _ in true },
            identifier: { $0 }
        )
    }

    func test_offeringSelection_experimentTreatmentCurrent_winsOverFallback() {
        let resolved = resolveOffering(
            current: "anicca_variant_b_hard",
            all: ["anicca_variant_b": "anicca_variant_b", "anicca_variant_b_hard": "anicca_variant_b_hard"]
        )
        XCTAssertEqual(resolved, "anicca_variant_b_hard")
    }

    func test_offeringSelection_experimentControlCurrent_wins() {
        let resolved = resolveOffering(
            current: "anicca_variant_b",
            all: ["anicca_variant_b": "anicca_variant_b", "anicca_variant_b_hard": "anicca_variant_b_hard"]
        )
        XCTAssertEqual(resolved, "anicca_variant_b")
    }

    func test_offeringSelection_legacyCurrent_fallsBackToConfigured() {
        let resolved = resolveOffering(
            current: "legacy_default",
            all: ["anicca_variant_b": "anicca_variant_b", "legacy_default": "legacy_default"]
        )
        XCTAssertEqual(resolved, "anicca_variant_b")
    }

    func test_offeringSelection_noCurrent_usesFallback() {
        let resolved = resolveOffering(
            current: nil,
            all: ["anicca_variant_b": "anicca_variant_b"]
        )
        XCTAssertEqual(resolved, "anicca_variant_b")
    }
}
