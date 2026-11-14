import XCTest
@testable import aniccaios

/// Phase 1 personalization: answer→change mapping rules, selector behavior,
/// and the onboarding journey order. These encode the contract of
/// `files/onboarding-answer-change-mapping-2026-11-14.md` (anicca-ops).
final class PersonalizationPhase1Tests: XCTestCase {

    private func syntheticUser(_ profile: PersonalizationProfile) -> SyntheticUser {
        SyntheticUser(profile: profile, personId: "test-person")
    }

    // MARK: - Schedule proposals

    func test_proposedFrequency_followsMapping() {
        XCTAssertEqual(PersonalizationRules.proposedFrequency(struggleFrequency: "rarely"), 1)
        XCTAssertEqual(PersonalizationRules.proposedFrequency(struggleFrequency: "weekly"), 1)
        XCTAssertEqual(PersonalizationRules.proposedFrequency(struggleFrequency: "daily"), 2)
        XCTAssertEqual(PersonalizationRules.proposedFrequency(struggleFrequency: "many_times_daily"), 3)
        XCTAssertEqual(PersonalizationRules.proposedFrequency(struggleFrequency: nil), 1)
    }

    func test_proposedSlots_defaultIsMorningFirst() {
        let slots = PersonalizationRules.proposedSlots(painPointIds: [], frequency: 2)
        XCTAssertEqual(slots, [NudgeSlot(hour: 8, minute: 0), NudgeSlot(hour: 12, minute: 30)])
    }

    func test_proposedSlots_sleepPainShiftsProposalToEvening() {
        let slots = PersonalizationRules.proposedSlots(painPointIds: ["sleep"], frequency: 2)
        XCTAssertEqual(slots, [NudgeSlot(hour: 17, minute: 30), NudgeSlot(hour: 21, minute: 30)])
    }

    func test_scheduleValidation_frequencyMustNotExceedSlots() {
        XCTAssertTrue(PersonalizationRules.isValidSchedule(
            slots: [NudgeSlot(hour: 8, minute: 0), NudgeSlot(hour: 21, minute: 30)], frequency: 2))
        XCTAssertFalse(PersonalizationRules.isValidSchedule(
            slots: [NudgeSlot(hour: 8, minute: 0)], frequency: 2))
        XCTAssertFalse(PersonalizationRules.isValidSchedule(slots: [], frequency: 1))
        XCTAssertFalse(PersonalizationRules.isValidSchedule(
            slots: [NudgeSlot(hour: 8, minute: 0), NudgeSlot(hour: 8, minute: 0)], frequency: 1))
    }

    func test_intensity_followsMapping() {
        XCTAssertEqual(PersonalizationRules.intensity(struggleFrequency: "rarely"), "gentle")
        XCTAssertEqual(PersonalizationRules.intensity(struggleFrequency: "weekly"), "gentle")
        XCTAssertEqual(PersonalizationRules.intensity(struggleFrequency: "daily"), "supportive")
        XCTAssertEqual(PersonalizationRules.intensity(struggleFrequency: "many_times_daily"), "supportive")
    }

    // MARK: - Category mapping

    func test_primaryCategory() {
        XCTAssertEqual(PersonalizationRules.primaryCategory(desiredState: "calm"), "calm")
        XCTAssertEqual(PersonalizationRules.primaryCategory(desiredState: "confidence"), "confidence")
        XCTAssertEqual(PersonalizationRules.primaryCategory(desiredState: "focus"), "presence")
        XCTAssertEqual(PersonalizationRules.primaryCategory(desiredState: "self_love"), "self_love")
        XCTAssertNil(PersonalizationRules.primaryCategory(desiredState: nil))
    }

    func test_problemTypeBridge_onlyTrueCounterparts() {
        XCTAssertEqual(PersonalizationRules.problemTypeBridge(painPointId: "anxiety"), "anxiety")
        XCTAssertEqual(PersonalizationRules.problemTypeBridge(painPointId: "procrastination"), "procrastination")
        XCTAssertEqual(PersonalizationRules.problemTypeBridge(painPointId: "self_doubt"), "self_loathing")
        XCTAssertNil(PersonalizationRules.problemTypeBridge(painPointId: "stress"))
        XCTAssertNil(PersonalizationRules.problemTypeBridge(painPointId: "sleep"))
    }

    // MARK: - Selector

    private var pool: [Quote] {
        [
            Quote(id: "growth.calm.0", text: "calm"),
            Quote(id: "growth.presence.0", text: "presence"),
            Quote(id: "growth.growth.0", text: "growth"),
            Quote(id: "growth.rest.0", text: "rest"),
        ]
    }

    /// Random source replaying a fixed sequence (last value repeats).
    private func sequenceRandom(_ values: [Double]) -> () -> Double {
        var index = 0
        return {
            defer { index += 1 }
            return values[min(index, values.count - 1)]
        }
    }

    func test_selector_desiredStateAndPainPointMatchWins() {
        let profile = PersonalizationProfile(desiredState: "calm", painPointIds: ["anxiety"])
        let selection = PersonalizedNudgeSelector.select(
            user: syntheticUser(profile), pool: pool, band: .day, random: sequenceRandom([0.99]))
        XCTAssertEqual(selection?.quote.id, "growth.calm.0")
        XCTAssertEqual(selection?.reason, "desired_state_and_pain_point_match")
        XCTAssertEqual(selection?.candidateCount, 4)
        XCTAssertEqual(selection?.assignedProbability ?? 0, 0.9 + 0.1 / 4, accuracy: 1e-9)
    }

    func test_selector_cooldownExcludesRecentlyShown() {
        let profile = PersonalizationProfile(desiredState: "calm", painPointIds: ["anxiety"])
        let selection = PersonalizedNudgeSelector.select(
            user: syntheticUser(profile), pool: pool,
            shownAt: ["growth.calm.0": Date()], band: .day, random: sequenceRandom([0.99]))
        XCTAssertEqual(selection?.quote.id, "growth.presence.0")
    }

    func test_selector_morningExcludesRestUnlessSleepPain() {
        let noSleep = PersonalizationProfile(desiredState: "calm")
        let morning = PersonalizedNudgeSelector.select(
            user: syntheticUser(noSleep), pool: pool, band: .morning, random: sequenceRandom([0.99]))
        XCTAssertEqual(morning?.candidateCount, 3)

        let withSleep = PersonalizationProfile(desiredState: "calm", painPointIds: ["sleep"])
        let morningSleep = PersonalizedNudgeSelector.select(
            user: syntheticUser(withSleep), pool: pool, band: .morning, random: sequenceRandom([0.99]))
        XCTAssertEqual(morningSleep?.candidateCount, 4)
    }

    func test_selector_explorationRecordsExactProbability() {
        let profile = PersonalizationProfile()
        let selection = PersonalizedNudgeSelector.select(
            user: syntheticUser(profile), pool: pool, band: .day, random: sequenceRandom([0.05, 0.999]))
        // Ranked order for an empty profile is by id; index 3 is the last.
        XCTAssertEqual(selection?.quote.id, "growth.rest.0")
        XCTAssertEqual(selection?.assignedProbability ?? 0, 0.1 / 4, accuracy: 1e-9)
    }

    // MARK: - Records

    func test_profileCodableRoundTrip() throws {
        let profile = PersonalizationProfile(
            preferredName: "Aki", desiredState: "focus",
            painPointIds: ["stress", "sleep"], struggleFrequency: "daily",
            nudgeSlots: [NudgeSlot(hour: 17, minute: 30), NudgeSlot(hour: 21, minute: 30)],
            dailyFrequency: 2, timezoneIdentifier: "Asia/Tokyo",
            updatedAt: Date(timeIntervalSince1970: 1_700_000_000))
        let data = try JSONEncoder().encode(profile)
        let decoded = try JSONDecoder().decode(PersonalizationProfile.self, from: data)
        XCTAssertEqual(decoded, profile)
    }

    func test_decisionRecordRequiresProbability() throws {
        let record = DecisionPointRecord(
            recordKind: "decision", personId: "p1", deliveryId: "d1",
            decisionPointAt: "2026-11-14T00:00:00Z", available: true,
            treatmentAssigned: "growth.calm.0", assignedProbability: 0.925,
            messageId: "growth.calm.0", policyVersion: "rule_v1",
            source: "onboarding_preview", desiredState: "calm",
            painPointIds: ["anxiety"], struggleFrequency: "daily",
            candidateCount: 4, selectionReason: "desired_state_and_pain_point_match",
            proximalOutcome: nil, outcomeWindowSec: 1800)
        let data = try JSONEncoder().encode(record)
        let decoded = try JSONDecoder().decode(DecisionPointRecord.self, from: data)
        XCTAssertEqual(decoded, record)
        XCTAssertEqual(decoded.assignedProbability, 0.925)
    }

    // MARK: - Journey

    func test_initialJourney_includesPainPointsAndFrequencyBeforePreview() {
        XCTAssertEqual(
            OnboardingStep.initialJourney,
            [.welcome, .goal, .name, .birthContext, .moodBaseline, .painPoints, .struggleFreq, .beliefThemes, .tone, .lifeContext, .routineAnchors, .priorAttempts, .startReason, .quietHours, .planReveal, .nudgeTimes, .notifications]
        )
        XCTAssertEqual(OnboardingStep.welcome.nextInitialStep, .goal)
        XCTAssertEqual(OnboardingStep.goal.nextInitialStep, .name)
        XCTAssertEqual(OnboardingStep.name.nextInitialStep, .birthContext)
        XCTAssertEqual(OnboardingStep.name.resumableInitialStep, .name)
        XCTAssertEqual(OnboardingStep.painPoints.nextInitialStep, .struggleFreq)
        XCTAssertEqual(OnboardingStep.struggleFreq.nextInitialStep, .beliefThemes)
        XCTAssertEqual(OnboardingStep.planReveal.nextInitialStep, .nudgeTimes)
        XCTAssertEqual(OnboardingStep.nudgeTimes.nextInitialStep, .notifications)
        XCTAssertNil(OnboardingStep.notifications.nextInitialStep)
    }
}

extension PersonalizationPhase1Tests {
    func test_permissionResultDoesNotEnableAdaptiveModeForLegacyResume() {
        for result in ["allowed", "denied", "skipped"] {
            var profile = PersonalizationProfile(desiredState: "calm")
            profile.recordNotificationPermission(result)
            XCTAssertNil(profile.adaptiveAnswers)
            XCTAssertFalse(syntheticUser(profile).hasAdaptiveAnswers)
            XCTAssertEqual(syntheticUser(profile).answerSnapshot.values["notification_permission"], ["unknown"])
        }
    }

    func test_permissionResultPreservesExistingAdaptiveAnswers() {
        var profile = PersonalizationProfile(desiredState: "calm")
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["mood_baseline": ["heavy"]])
        profile.recordNotificationPermission("denied")
        XCTAssertEqual(profile.answers.ids(for: .moodBaseline), ["heavy"])
        XCTAssertEqual(syntheticUser(profile).answerSnapshot.values["notification_permission"], ["denied"])
        XCTAssertTrue(syntheticUser(profile).hasAdaptiveAnswers)
    }

    func test_birthDateDoesNotMasqueradeAsZodiacSelectionAfterReload() throws {
        let date = ISO8601DateFormatter().date(from: "1990-05-15T00:00:00Z")!
        var answers = AdaptiveAnswers(values: ["birth_context": ["scorpio"]])
        answers.setBirthContext(birthDate: date, zodiacIDs: ["scorpio"])
        let restored = try JSONDecoder().decode(AdaptiveAnswers.self, from: JSONEncoder().encode(answers))
        XCTAssertEqual(restored.birthDate, date)
        XCTAssertEqual(restored.ids(for: .birthContext), [])
        XCTAssertEqual(restored.values["birth_context"], ["unknown"])
        var profile = PersonalizationProfile()
        profile.adaptiveAnswers = restored
        XCTAssertEqual(profile.answerSnapshot().values["birth_context"], ["date_provided"])

        answers.setBirthContext(birthDate: nil, zodiacIDs: ["taurus"])
        XCTAssertNil(answers.birthDate)
        XCTAssertEqual(answers.ids(for: .birthContext), ["taurus"])
        answers.setBirthContext(birthDate: nil, zodiacIDs: [])
        XCTAssertNil(answers.birthDate)
        XCTAssertEqual(answers.ids(for: .birthContext), [])
    }

    func test_adaptiveModules_followPresentationOrderAndLimitToTwo() {
        XCTAssertEqual(OnboardingStep.deepDiveSteps(painPointIds: ["sleep", "anxiety"]),
                       [.anxietyTarget, .sleepReason, .bedtime, .wakeTime])
        XCTAssertEqual(OnboardingStep.deepDiveSteps(painPointIds: ["sleep", "procrastination", "self_doubt", "anxiety", "stress"]),
                       [.stressTrigger, .anxietyTarget])
        XCTAssertEqual(OnboardingStep.deepDiveSteps(painPointIds: ["sleep", "sleep", "unknown"]),
                       [.sleepReason, .bedtime, .wakeTime])
        XCTAssertTrue(OnboardingStep.deepDiveSteps(painPointIds: []).isEmpty)
    }

    func test_adaptiveJourney_insertsOnlySelectedModulesImmediatelyAfterPain() {
        let journey = OnboardingStep.journey(painPointIds: ["sleep", "anxiety"])
        let pain = journey.firstIndex(of: .painPoints)!
        XCTAssertEqual(Array(journey[(pain + 1)...(pain + 4)]), [.anxietyTarget, .sleepReason, .bedtime, .wakeTime])
        XCTAssertEqual(journey[pain + 5], .struggleFreq)
        XCTAssertFalse(journey.contains(.stressTrigger))
        XCTAssertFalse(journey.contains(.avoidanceTask))
        XCTAssertEqual(OnboardingStep.sleepReason.resumableStep(painPointIds: ["stress"]), .struggleFreq)
    }

    func test_newRawValuesPreserveRoundOneAndLegacyMigration() {
        XCTAssertEqual(OnboardingStep.name.rawValue, 9)
        XCTAssertEqual(OnboardingStep.birthContext.rawValue, 10)
        XCTAssertEqual(OnboardingStep.wakeTime.rawValue, 25)
        XCTAssertEqual(OnboardingStep.priorHelpfulness.rawValue, 26)
        for raw in 0...9 { XCTAssertEqual(OnboardingStep(rawValue: raw)?.rawValue, raw) }
        XCTAssertEqual(OnboardingStep.migratedFromV7RawValue(9), .notifications)
        XCTAssertEqual(OnboardingStep.migratedFromV6RawValue(10)?.resumableInitialStep, .planReveal)
    }

    func test_heavyMoodAlwaysChoosesGentlerIntensity() {
        for frequency in ["rarely", "weekly", "daily", "many_times_daily"] {
            for mood in ["very_heavy", "heavy"] {
                XCTAssertEqual(PersonalizationRules.intensity(struggleFrequency: frequency, moodBaseline: mood), "gentle")
            }
        }
        XCTAssertEqual(PersonalizationRules.intensity(struggleFrequency: "weekly", moodBaseline: "very_light"), "gentle")
        XCTAssertEqual(PersonalizationRules.intensity(struggleFrequency: "daily", moodBaseline: "neutral"), "supportive")
    }

    func test_quietHoursOverrideExplicitTimesWithoutAddingReplacements() {
        var profile = PersonalizationProfile(nudgeSlots: [.init(hour: 8, minute: 0), .init(hour: 21, minute: 30)], dailyFrequency: 2)
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["routine_anchors": ["lunch"], "quiet_hours": ["evening"]])
        XCTAssertEqual(PersonalizationRules.effectiveSlots(profile: profile), [.init(hour: 8, minute: 0)])
        XCTAssertEqual(profile.nudgeSlots.count, 2, "Keep the original explicit answer for replay")
        profile.adaptiveAnswers?.values["quiet_hours"] = ["morning", "afternoon", "evening", "overnight"]
        XCTAssertEqual(PersonalizationRules.effectiveSlots(profile: profile), [])
    }

    func test_quietHoursUseHalfOpenRangesAndWrapMidnight() {
        for hour in [22, 23, 0, 5] {
            XCTAssertTrue(PersonalizationRules.isQuiet(.init(hour: hour, minute: 0), quietHours: ["overnight"]))
        }
        XCTAssertFalse(PersonalizationRules.isQuiet(.init(hour: 6, minute: 0), quietHours: ["overnight"]))
        XCTAssertTrue(PersonalizationRules.isQuiet(.init(hour: 6, minute: 0), quietHours: ["morning"]))
        XCTAssertFalse(PersonalizationRules.isQuiet(.init(hour: 12, minute: 0), quietHours: ["morning"]))
        XCTAssertFalse(PersonalizationRules.isQuiet(.init(hour: 22, minute: 0), quietHours: ["evening"]))
    }

    func test_anchorsOnlyProposeWhenNoExplicitScheduleExists() {
        var profile = PersonalizationProfile(painPointIds: ["sleep"], nudgeSlots: [.init(hour: 8, minute: 0)])
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["routine_anchors": ["bedtime"]])
        XCTAssertEqual(PersonalizationRules.initialSlots(profile: profile, frequency: 1), [.init(hour: 8, minute: 0)])
        profile.nudgeSlots = []
        XCTAssertEqual(PersonalizationRules.initialSlots(profile: profile, frequency: 1), [.init(hour: 21, minute: 30)])
    }

    func test_skippedAndUnaskedAnswersRemainMissingAndPrivateValuesNeverReachSnapshot() throws {
        var profile = PersonalizationProfile(preferredName: "Private Name", desiredState: "calm", painPointIds: ["anxiety"])
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["birth_context": ["unknown"], "anxiety_target": ["money"]])
        let missing = profile.answerSnapshot()
        XCTAssertEqual(missing.values["birth_context"], ["unknown"])
        XCTAssertEqual(missing.values["stress_trigger"], ["not_asked"])
        XCTAssertEqual(missing.values["age_band"], ["unknown"])
        profile.adaptiveAnswers?.birthDate = ISO8601DateFormatter().date(from: "1990-05-15T00:00:00Z")
        profile.adaptiveAnswers?.values["birth_context"] = ["date_provided"]
        profile.adaptiveAnswers?.values["tone"] = ["some injected free text"]
        let snapshot = profile.answerSnapshot(now: ISO8601DateFormatter().date(from: "2026-11-14T12:00:00Z")!)
        XCTAssertEqual(snapshot.values["age_band"], ["35_44"])
        XCTAssertEqual(snapshot.values["tone"], ["unknown"])
        let json = String(data: try JSONEncoder().encode(snapshot), encoding: .utf8)!
        for privateValue in ["Private Name", "1990", "birthDate", "injected free text"] {
            XCTAssertFalse(json.contains(privateValue))
        }
    }

    func test_roundOneProfileDecodesWithoutNewFieldsAndUserProfileKeepsAnswers() throws {
        let old = Data(#"{"painPointIds":["sleep"],"nudgeSlots":[],"dailyFrequency":1,"timezoneIdentifier":"UTC","schemaVersion":1,"updatedAt":0}"#.utf8)
        let migrated = try JSONDecoder().decode(PersonalizationProfile.self, from: old)
        XCTAssertEqual(migrated.painPointIds, ["sleep"])
        XCTAssertNil(migrated.adaptiveAnswers)
        var profile = UserProfile()
        var personalization = migrated
        personalization.adaptiveAnswers = AdaptiveAnswers(values: ["sleep_reason": ["screens"], "bedtime": ["after_midnight"]])
        profile.personalization = personalization
        let decoded = try JSONDecoder().decode(UserProfile.self, from: JSONEncoder().encode(profile))
        XCTAssertEqual(decoded.personalization, personalization)
        XCTAssertNil(try JSONDecoder().decode(UserProfile.self, from: Data("{}".utf8)).personalization)
    }
}

extension PersonalizationPhase1Tests {
    func test_explorationCannotEscapeHeavyMoodToneOrContextConstraints() throws {
        var profile = PersonalizationProfile(desiredState: "calm", struggleFrequency: "daily")
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["mood_baseline": ["heavy"], "tone": ["direct"], "life_context": ["none"]])
        let candidates = AdaptiveAffirmationCatalog.quotes(language: .en)
        for sample in [0.0, 0.3, 0.6, 0.999] {
            let result = try XCTUnwrap(PersonalizedNudgeSelector.select(user: syntheticUser(profile), pool: candidates, band: .day, random: sequenceRandom([0.01, sample])))
            let traits = try XCTUnwrap(AdaptiveAffirmationCatalog.traits(for: result.quote))
            XCTAssertEqual(traits.intensity, "gentle")
            XCTAssertEqual(traits.tone, "direct")
            XCTAssertTrue(traits.contexts.isEmpty)
            XCTAssertGreaterThan(result.assignedProbability, 0)
        }
    }

    func test_selectorExcludesWrongAnxietyTargetAndUnhelpfulMethods() {
        var profile = PersonalizationProfile(painPointIds: ["anxiety"])
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["anxiety_target": ["health"], "prior_attempts": ["meditation"], "prior_helpfulness": ["meditation"]])
        let pool = AdaptiveAffirmationCatalog.quotes(language: .en)
        let eligible = pool.filter { PersonalizedNudgeSelector.isEligible(quote: $0, user: syntheticUser(profile), band: .day) }
        XCTAssertTrue(eligible.contains { $0.id == "adaptive.calm.anxiety_health" })
        XCTAssertFalse(eligible.contains { $0.id == "adaptive.presence.anxiety_money" })
        XCTAssertFalse(eligible.contains { $0.id == "adaptive.presence.method_meditation" })
        XCTAssertFalse(eligible.contains { $0.id == "adaptive.growth.action_work" })
    }

    func test_beliefThemeAddsWeightWithoutReplacingPrimaryGoal() throws {
        let quotes = AdaptiveAffirmationCatalog.quotes(language: .en)
        let calm = try XCTUnwrap(quotes.first { $0.id == "adaptive.calm.calm_gentle" })
        let confidence = try XCTUnwrap(quotes.first { $0.id == "adaptive.confidence.confidence_gentle" })
        var profile = PersonalizationProfile(desiredState: "calm")
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["belief_themes": ["self_trust"]])
        let boosted = PersonalizedNudgeSelector.score(quote: confidence, user: syntheticUser(profile))
        XCTAssertGreaterThan(PersonalizedNudgeSelector.score(quote: calm, user: syntheticUser(profile)), boosted)
        profile.adaptiveAnswers?.values["belief_themes"] = ["inner_peace"]
        XCTAssertGreaterThan(boosted, PersonalizedNudgeSelector.score(quote: confidence, user: syntheticUser(profile)))
    }

    func test_decisionSnapshotRoundTripsAndOldRecordStillDecodes() throws {
        var record = DecisionPointRecord(recordKind: "decision", personId: "p", deliveryId: "d", decisionPointAt: "2026-11-14T00:00:00Z", available: true, treatmentAssigned: "q029", assignedProbability: 1, messageId: "q029", policyVersion: "rule_v2_adaptive", source: "onboarding_preview", painPointIds: [], outcomeWindowSec: 1800)
        var profile = PersonalizationProfile()
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["mood_baseline": ["heavy"]])
        record.answerSnapshot = profile.answerSnapshot()
        let encoded = try JSONEncoder().encode(record)
        XCTAssertEqual(try JSONDecoder().decode(DecisionPointRecord.self, from: encoded).answerSnapshot?.values["mood_baseline"], ["heavy"])
        var legacy = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        legacy.removeValue(forKey: "answerSnapshot")
        XCTAssertNil(try JSONDecoder().decode(DecisionPointRecord.self, from: JSONSerialization.data(withJSONObject: legacy)).answerSnapshot)
    }
}

extension PersonalizationPhase1Tests {
    func test_priorExperienceDoesNotImplyFailureAndOnlyTriedMethodsAreFollowUps() {
        var answers = AdaptiveAnswers()
        answers.set(.priorAttempts, ids: ["meditation", "journaling"])
        XCTAssertEqual(OnboardingQuestion.priorHelpfulness.options(answers: answers), ["meditation", "journaling", "none"])
        XCTAssertEqual(answers.ids(for: .priorHelpfulness), [])
        XCTAssertTrue(OnboardingStep.journey(painPointIds: [], priorAttempts: ["meditation"]).contains(.priorHelpfulness))
        XCTAssertFalse(OnboardingStep.journey(painPointIds: [], priorAttempts: ["first_time"]).contains(.priorHelpfulness))
    }

    func test_noneSelectionCannotCoexistWithContextOrQuietHours() {
        var answers = AdaptiveAnswers()
        answers.set(.lifeContext, ids: ["work", "none"])
        XCTAssertEqual(answers.ids(for: .lifeContext), ["none"])
        answers.set(.quietHours, ids: ["morning", "none"])
        XCTAssertEqual(answers.ids(for: .quietHours), ["none"])
    }

    func test_sleepProposalUsesBedtimeOnlyUntilExplicitChoice() {
        var profile = PersonalizationProfile(painPointIds: ["sleep"])
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["bedtime": ["before_22"]])
        XCTAssertEqual(PersonalizationRules.initialSlots(profile: profile, frequency: 1), [.init(hour: 17, minute: 30)])
        profile.nudgeSlots = [.init(hour: 12, minute: 30)]
        XCTAssertEqual(PersonalizationRules.initialSlots(profile: profile, frequency: 1), [.init(hour: 12, minute: 30)])
    }

    func test_heavyMoodExcludesSupportiveCandidateButLightMoodCanChooseIt() throws {
        var profile = PersonalizationProfile(desiredState: "calm", struggleFrequency: "daily")
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["mood_baseline": ["light"], "tone": ["direct"]])
        let pool = AdaptiveAffirmationCatalog.quotes(language: .en)
        let light = try XCTUnwrap(PersonalizedNudgeSelector.select(user: syntheticUser(profile), pool: pool, band: .day, random: { 0.99 }))
        XCTAssertEqual(light.quote.id, "adaptive.calm.calm_supportive")
        profile.adaptiveAnswers?.values["mood_baseline"] = ["heavy"]
        let heavy = try XCTUnwrap(PersonalizedNudgeSelector.select(user: syntheticUser(profile), pool: pool, band: .day, random: { 0.99 }))
        XCTAssertEqual(heavy.quote.id, "adaptive.calm.calm_direct")
    }

    func test_milestoneIsCalendarContextAndSkippedBirthNeverInfersIt() {
        let date = ISO8601DateFormatter().date(from: "2026-11-14T12:00:00Z")!
        let skipped = AdaptiveAnswers(values: ["birth_context": ["unknown"]])
        XCTAssertFalse(skipped.isBirthdaySeason(now: date))
        let zodiac = AdaptiveAnswers(values: ["birth_context": ["scorpio"]])
        XCTAssertTrue(zodiac.isBirthdaySeason(now: date))
        XCTAssertEqual(zodiac.ageBand(now: date), "unknown")
    }

    @MainActor
    func test_progressIncludesOnlyTheActiveQuestions() {
        let journey = OnboardingStep.journey(painPointIds: ["sleep", "anxiety"], priorAttempts: ["meditation"])
        XCTAssertEqual(journey.count, 22)
        XCTAssertEqual(OnboardingProgressBar.progress(for: .anxietyTarget, journey: journey), 7.0 / 22, accuracy: 0.001)
        XCTAssertEqual(OnboardingProgressBar.progress(for: .notifications, journey: journey), 1)
    }
}

extension PersonalizationPhase1Tests {
    func test_deliveryPayloadSuppressesQuietSlotsAndNeverExportsNameOrBirthDate() throws {
        var profile = PersonalizationProfile(preferredName: "Private Name", nudgeSlots: [.init(hour: 21, minute: 30)])
        profile.adaptiveAnswers = AdaptiveAnswers(values: ["quiet_hours": ["evening"], "birth_context": ["date_provided"]], birthDate: Date(timeIntervalSince1970: 0))
        let payload = syntheticUser(profile).deliveryPayload(timezoneIdentifier: "UTC")
        XCTAssertEqual(payload["nudgeSlots"] as? [String], [])
        XCTAssertEqual(payload["dailyFrequency"] as? Int, 0)
        XCTAssertEqual(payload["answerVersion"] as? Int, 4)
        let json = String(data: try JSONSerialization.data(withJSONObject: payload), encoding: .utf8)!
        XCTAssertFalse(json.contains("Private Name"))
        XCTAssertFalse(json.contains("birthDate"))
        XCTAssertFalse(json.contains("1970"))
        XCTAssertFalse(profile.answerSnapshot().analyticsIDs.contains { $0.contains("Private Name") })
    }
}

extension PersonalizationPhase1Tests {
    func test_profileSyncBufferKeepsAnswersArrivingDuringAnOlderSend() throws {
        var buffer = ProfileSyncBuffer()
        var first = UserProfile()
        first.personalization = PersonalizationProfile(desiredState: "calm")
        buffer.enqueue(first)
        let inFlight = try XCTUnwrap(buffer.take())
        var latest = first
        latest.personalization?.adaptiveAnswers = AdaptiveAnswers(values: ["quiet_hours": ["overnight"]])
        buffer.enqueue(latest)
        // An older failure may not replace a newer answer either.
        buffer.restoreUnlessNewer(inFlight)
        XCTAssertEqual(buffer.take()?.personalization?.answers.ids(for: .quietHours), ["overnight"])
        XCTAssertNil(buffer.take())
        buffer.restoreUnlessNewer(inFlight)
        XCTAssertEqual(buffer.take()?.personalization?.desiredState, "calm")
    }
}
