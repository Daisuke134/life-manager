import XCTest
@testable import aniccaios

final class SyntheticUserTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_794_614_400)

    private func profile() -> PersonalizationProfile {
        var profile = PersonalizationProfile(
            preferredName: "Private Name", desiredState: "calm", painPointIds: ["anxiety"],
            struggleFrequency: "daily", nudgeSlots: [.init(hour: 8, minute: 0), .init(hour: 21, minute: 30)],
            dailyFrequency: 2)
        var answers = AdaptiveAnswers()
        answers.birthDate = Date(timeIntervalSince1970: 631_152_000)
        answers.set(.moodBaseline, ids: ["heavy"])
        answers.set(.lifeContext, ids: ["caregiving"])
        answers.set(.beliefThemes, ids: ["inner_peace"])
        answers.set(.anxietyTarget, ids: ["future"])
        answers.set(.routineAnchors, ids: ["waking"])
        answers.set(.quietHours, ids: ["evening"])
        answers.set(.startReason, ids: ["overwhelmed"])
        answers.set(.tone, ids: ["gentle"])
        profile.adaptiveAnswers = answers
        return profile
    }

    func test_recordContainsStructuredAxesWithoutNameBirthDateOrUnknownFreeText() throws {
        var profile = profile()
        profile.adaptiveAnswers?.values["untrusted"] = ["private diary"]
        profile.adaptiveAnswers?.values["life_context"]?.append("private employer")
        let user = SyntheticUser(profile: profile, personId: "p1", now: now)
        XCTAssertEqual(user.attributes["age_band"], ["35_44"])
        XCTAssertEqual(user.attributes["life_context"], ["caregiving"])
        XCTAssertEqual(user.initialState["mood_baseline"], ["heavy"])
        XCTAssertEqual(user.beliefThemes, ["inner_peace"])
        XCTAssertEqual(user.triggerContext["anxiety_target"], ["future"])
        XCTAssertEqual(user.receptivityWindows["routine_anchors"], ["waking"])
        XCTAssertEqual(user.quietHours, ["evening"])
        XCTAssertEqual(user.motivation["start_reason"], ["overwhelmed"])
        let json = String(decoding: try JSONEncoder().encode(user), as: UTF8.self)
        for forbidden in ["Private Name", "birthDate", "631152000", "private diary", "private employer"] {
            XCTAssertFalse(json.contains(forbidden), forbidden)
        }
    }

    func test_persistReloadAndAnswerRefreshKeepInterventionHistory() throws {
        let suite = "SyntheticUserTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = SyntheticUserStore(defaults: defaults)
        var user = store.refresh(profile: profile(), now: now)
        user.recordIntervention(messageId: "adaptive.calm.calm_gentle", deliveryId: "d1", event: "saved", at: now)
        store.save(user)
        var changed = profile()
        changed.desiredState = "confidence"
        let reloaded = SyntheticUserStore(defaults: defaults).refresh(profile: changed, now: now)
        XCTAssertEqual(reloaded.personId, user.personId)
        XCTAssertEqual(reloaded.motivation["desired_state"], ["confidence"])
        XCTAssertEqual(reloaded.interventionHistory.count, 1)
        XCTAssertEqual(reloaded.interventionHistory.first?.event, .saved)
    }

    func test_storeLoadAcceptsCurrentAndCompatiblePreviousSchemaButRejectsUnknownVersions() throws {
        let suite = "SyntheticUserTests.Schema.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = SyntheticUserStore(defaults: defaults)
        let legacy = SyntheticUser.LegacySignals(goals: ["reduce_anxiety"], problems: [], likedIDs: [], recentIDs: [])
        let current = try JSONSerialization.jsonObject(with: JSONEncoder().encode(
            SyntheticUser(profile: profile(), personId: "p1", legacySignals: legacy, now: now))) as! [String: Any]

        for version in [1, 2] {
            var payload = current
            payload["schemaVersion"] = version
            if version == 1 { payload.removeValue(forKey: "legacySignals") }
            defaults.set(try JSONSerialization.data(withJSONObject: payload), forKey: "com.anicca.syntheticUser")
            XCTAssertEqual(store.load()?.personId, "p1", "schema version \(version)")
        }

        let rejectedVersions: [Any] = [0, 3, "future"]
        for rejectedVersion in rejectedVersions {
            var payload = current
            payload["schemaVersion"] = rejectedVersion
            defaults.set(try JSONSerialization.data(withJSONObject: payload), forKey: "com.anicca.syntheticUser")
            XCTAssertNil(store.load(), "rejected schema version: \(String(describing: rejectedVersion))")
        }

        var missing = current
        missing.removeValue(forKey: "schemaVersion")
        defaults.set(try JSONSerialization.data(withJSONObject: missing), forKey: "com.anicca.syntheticUser")
        XCTAssertNil(store.load(), "missing schema version")
    }

    func test_recordedUserRemainsTheInputAfterMaterialProfileChanges() {
        var material = profile()
        let user = SyntheticUser(profile: material, personId: "p1", now: now)
        material.desiredState = "confidence"
        material.adaptiveAnswers?.set(.quietHours, ids: ["none"])
        XCTAssertEqual(PersonalizationRules.effectiveSlots(user: user), [.init(hour: 8, minute: 0)])
        let selection = PersonalizedNudgeSelector.select(
            user: user, pool: AdaptiveAffirmationCatalog.quotes(language: .en),
            now: now, band: .day, random: { 0.99 })
        XCTAssertEqual(selection?.quote.categoryID, "calm")
        XCTAssertEqual(selection.flatMap { AdaptiveAffirmationCatalog.traits(for: $0.quote)?.intensity }, "gentle")
    }

    func test_signOutClearsHistoryAndRotatesPseudonym() throws {
        let suite = "SyntheticUserTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = SyntheticUserStore(defaults: defaults)
        let old = store.refresh(profile: profile(), now: now)
        store.clear()
        let fresh = store.refresh(profile: PersonalizationProfile(), now: now)
        XCTAssertNotEqual(old.personId, fresh.personId)
        XCTAssertFalse(fresh.hasAnswers)
        XCTAssertTrue(fresh.interventionHistory.isEmpty)
    }

    func test_repeatedObservationIsIdempotentAndInvalidEventsAreNotStored() {
        var user = SyntheticUser(profile: profile(), personId: "p1", now: now)
        for _ in 0..<2 {
            user.recordIntervention(messageId: "adaptive.calm.calm_gentle", deliveryId: "d1", event: "saved", at: now)
        }
        user.recordIntervention(messageId: "private text", deliveryId: "d2", event: "free text", at: now)
        XCTAssertEqual(user.interventionHistory.count, 1)
    }

    func test_unaskedTriggerIsNotPromotedIntoTheSyntheticUser() {
        var material = profile()
        material.adaptiveAnswers?.set(.stressTrigger, ids: ["work"])
        let user = SyntheticUser(profile: material, personId: "p1", now: now)
        XCTAssertEqual(user.triggerContext["stress_trigger"], ["not_asked"])
    }

    func test_laterSaveDoesNotExtendMessageCooldown() {
        var user = SyntheticUser(profile: profile(), personId: "p1", now: now)
        user.recordIntervention(messageId: "adaptive.calm.calm_gentle", deliveryId: "d1", event: "assigned", at: now)
        user.recordIntervention(messageId: "adaptive.calm.calm_gentle", deliveryId: "d1", event: "saved", at: now.addingTimeInterval(86_400))
        XCTAssertEqual(user.shownTimestamps["adaptive.calm.calm_gentle"], now)
    }

    func test_upgradeImportsOnlyThisPersonsDatedEvidenceAndDoesNotDuplicateItOnRestart() throws {
        let suite = "SyntheticUserTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { defaults.removePersistentDomain(forName: suite); try? FileManager.default.removeItem(at: directory) }
        defaults.set("current-person", forKey: "com.anicca.decisionPersonId")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let old = DecisionPointRecord(
            recordKind: "decision", personId: "current-person", deliveryId: "old-decision",
            decisionPointAt: "2026-11-13T00:00:00Z", available: true, treatmentAssigned: "q021",
            assignedProbability: 0.9, messageId: "q021", policyVersion: "rule_v2_adaptive",
            source: "daily_home", painPointIds: [], proximalOutcome: "saved", outcomeWindowSec: 1800)
        try JSONEncoder().encode(old).write(to: directory.appendingPathComponent("decision-points.jsonl"))
        let journal = DecisionPointStore(directory: directory)
        let deliveredAt = now.addingTimeInterval(-600)
        let respondedAt = now.addingTimeInterval(-86_280)
        XCTAssertTrue(journal.recordResponse(personId: "current-person", deliveryId: "old-decision", event: .responded, at: respondedAt, messageId: "q021"))
        XCTAssertTrue(journal.recordResponse(personId: "current-person", deliveryId: "pending", event: .notificationDelivered, at: deliveredAt, messageId: "q022"))
        XCTAssertTrue(journal.recordResponse(personId: "other-person", deliveryId: "other", event: .notificationDelivered, at: deliveredAt, messageId: "q023"))
        let history = journal.syntheticInterventionHistory(personId: "current-person")
        let first = SyntheticUserStore(defaults: defaults).refresh(profile: PersonalizationProfile(), observedHistory: history, now: now)
        XCTAssertEqual(first.shownTimestamps["q021"], now.addingTimeInterval(-86_400))
        XCTAssertEqual(first.shownTimestamps["q022"], deliveredAt)
        XCTAssertNil(first.shownTimestamps["q023"])
        XCTAssertEqual(first.interventionHistory.first { $0.deliveryId == "old-decision" && $0.event == .responded }?.observedAt, respondedAt)
        XCTAssertFalse(first.interventionHistory.contains { $0.event == .saved }, "Legacy positive has no measured timestamp")
        let second = SyntheticUserStore(defaults: defaults).refresh(profile: PersonalizationProfile(), observedHistory: history, now: now)
        XCTAssertEqual(first.interventionHistory, second.interventionHistory)
        let selection = PersonalizedNudgeSelector.select(user: second, pool: [Quote(id: "q021", text: "Seen"), Quote(id: "q024", text: "Unseen")], now: now, band: .day, random: { 0.99 })
        XCTAssertEqual(selection?.quote.id, "q024")
    }

    func test_legacyGoalsProblemsLikesAndRecentIDsRemainUsefulWithoutFabricatedDates() throws {
        let pool = [Quote(id: "q001", text: "Growth"), Quote(id: "q021", text: "Seen calm"), Quote(id: "q022", text: "Unseen calm")]
        for signals in [
            SyntheticUser.LegacySignals(goals: ["reduce_anxiety"], problems: [], likedIDs: [], recentIDs: ["q021"]),
            SyntheticUser.LegacySignals(goals: [], problems: ["anxiety"], likedIDs: [], recentIDs: ["q021"]),
            SyntheticUser.LegacySignals(goals: [], problems: [], likedIDs: ["q021"], recentIDs: ["q021"])
        ] {
            let user = SyntheticUser(profile: PersonalizationProfile(), personId: "p1", legacySignals: signals, now: now)
            let selection = PersonalizedNudgeSelector.select(user: user, pool: pool, now: now, band: .day, random: { 0.99 })
            XCTAssertEqual(selection?.quote.id, "q022")
            XCTAssertTrue(user.interventionHistory.isEmpty)
            XCTAssertTrue(user.shownTimestamps.isEmpty)
        }
    }

    func test_legacyMaterialCannotOverrideExplicitAnswersOrExportFreeText() throws {
        let signals = SyntheticUser.LegacySignals(goals: ["confidence", "private diary"], problems: ["anxiety", "private employer"], likedIDs: ["q021", "private name"], recentIDs: ["q022", "private text"])
        let user = SyntheticUser(profile: PersonalizationProfile(desiredState: "focus"), personId: "p1", legacySignals: signals, now: now)
        let selection = PersonalizedNudgeSelector.select(user: user, pool: [Quote(id: "q021", text: "Calm"), Quote(id: "q031", text: "Presence"), Quote(id: "q041", text: "Confidence")], now: now, band: .day, random: { 0.99 })
        XCTAssertEqual(selection?.quote.id, "q031")
        XCTAssertEqual(user.motivation["desired_state"], ["focus"])
        let json = String(decoding: try JSONEncoder().encode(user), as: UTF8.self)
        for text in ["private diary", "private employer", "private name", "private text"] { XCTAssertFalse(json.contains(text)) }
    }
}
