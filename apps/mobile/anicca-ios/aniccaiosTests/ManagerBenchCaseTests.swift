import XCTest
@testable import aniccaios

final class ManagerBenchCaseTests: XCTestCase {
    private let instant = Date(timeIntervalSince1970: 1_700_000_000)

    private func fixture() -> ManagerBenchCase {
        ManagerBenchCase(
            personId: "person-1", deliveryId: "delivery-1", decisionPointAt: instant,
            source: "onboarding_first_intervention", outcomeWindowSec: 1800,
            situation: .init(answerSnapshot: ["mood_baseline": ["heavy"]], answerVersion: 2,
                             scheduledTimeBand: "night", weekday: "tuesday", notificationPermission: "allowed"),
            stimulus: .init(messageId: "adaptive.calm.calm_gentle", category: "calm", tags: ["gentle"],
                            scheduledAt: instant, treatmentAssigned: "adaptive.calm.calm_gentle",
                            assignedProbability: 0.925, policyVersion: "rule_v2_adaptive")
        )
    }

    private func makeStore() -> (DecisionPointStore, URL) {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        return (DecisionPointStore(directory: dir), dir)
    }

    func testEncodedCaseHasThreeElementsAndExplicitUnknownResponses() throws {
        let data = try ManagerBenchCase.encoder.encode(fixture())
        let row = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(row["person_id"] as? String, "person-1")
        XCTAssertNotNil(row["situation"])
        let stimulus = try XCTUnwrap(row["stimulus"] as? [String: Any])
        XCTAssertEqual(stimulus["assigned_probability"] as? Double, 0.925)
        XCTAssertTrue(stimulus["delivered_at"] is NSNull)
        let response = try XCTUnwrap(row["response"] as? [String: Any])
        XCTAssertTrue(response["notification_delivered"] is NSNull)
        XCTAssertTrue(response["saved"] is NSNull)
        XCTAssertTrue(response["saved_at"] is NSNull)
        XCTAssertEqual(try ManagerBenchCase.decoder.decode(ManagerBenchCase.self, from: data), fixture())
    }

    func testResponseJoinsSameRowSurvivesReloadAndDoesNotOverwriteEarlierEvents() throws {
        let (store, dir) = makeStore()
        defer { try? FileManager.default.removeItem(at: dir) }
        XCTAssertTrue(store.append(fixture()))
        XCTAssertTrue(store.recordResponse(personId: "person-1", deliveryId: "delivery-1", event: .saved, at: instant.addingTimeInterval(10)))
        XCTAssertTrue(store.recordResponse(personId: "person-1", deliveryId: "delivery-1", event: .shared, at: instant.addingTimeInterval(20)))
        let loaded = DecisionPointStore(directory: dir).allCases()
        XCTAssertEqual(loaded.count, 1)
        XCTAssertEqual(loaded[0].response.saved, true)
        XCTAssertEqual(loaded[0].response.shared, true)
        XCTAssertEqual(loaded[0].response.savedAt, instant.addingTimeInterval(10))
        XCTAssertNil(loaded[0].response.notificationDelivered)
    }

    func testWindowClosureOnlyMarksObservableAbsenceFalseAndLateEventsDoNotRewriteWindow() {
        var row = fixture()
        row.closeObservationWindow(at: instant.addingTimeInterval(1799))
        XCTAssertNil(row.response.saved)
        row.closeObservationWindow(at: instant.addingTimeInterval(1800))
        XCTAssertEqual(row.response.saved, false)
        XCTAssertEqual(row.response.responded, false)
        XCTAssertNil(row.response.savedAt)
        XCTAssertNil(row.response.notificationDelivered)
        XCTAssertNil(row.response.notificationOpened)
        row.observe(.saved, at: instant.addingTimeInterval(2000))
        XCTAssertEqual(row.response.saved, false)
        XCTAssertNil(row.response.savedAt)
    }

    func testWindowClosureInfersAppOpenOnlyForNotificationSource() {
        var notification = fixture()
        notification.source = "notification"
        notification.closeObservationWindow(at: instant.addingTimeInterval(1800))
        XCTAssertEqual(notification.response.appOpened, false)

        var home = fixture()
        home.source = "daily_home"
        home.closeObservationWindow(at: instant.addingTimeInterval(1800))
        XCTAssertNil(home.response.appOpened)

        var onboarding = fixture()
        onboarding.source = "onboarding_first_intervention"
        onboarding.closeObservationWindow(at: instant.addingTimeInterval(1800))
        XCTAssertNil(onboarding.response.appOpened)

        var onboardingPreview = fixture()
        onboardingPreview.source = "onboarding_preview"
        onboardingPreview.closeObservationWindow(at: instant.addingTimeInterval(1800))
        XCTAssertNil(onboardingPreview.response.appOpened)

        var observed = fixture()
        observed.source = "daily_home"
        observed.observe(.appOpened, at: instant.addingTimeInterval(30))
        observed.closeObservationWindow(at: instant.addingTimeInterval(1800))
        XCTAssertEqual(observed.response.appOpened, true)
        XCTAssertEqual(observed.response.appOpenedAt, instant.addingTimeInterval(30))
    }

    func testPendingObservationIsNotAnEvalCaseUntilAssignmentArrives() {
        let (store, dir) = makeStore()
        defer { try? FileManager.default.removeItem(at: dir) }
        XCTAssertTrue(store.recordResponse(personId: "person-1", deliveryId: "delivery-1", event: .notificationOpened, at: instant.addingTimeInterval(12)))
        XCTAssertTrue(store.allCases().isEmpty)
        XCTAssertEqual(store.pendingObservations().count, 1)
        XCTAssertTrue(store.append(fixture()))
        XCTAssertTrue(store.pendingObservations().isEmpty)
        XCTAssertEqual(store.allCases().first?.response.notificationOpened, true)
        XCTAssertEqual(store.allCases().first?.response.notificationOpenedAt, instant.addingTimeInterval(12))
    }

    func testPersonBoundaryPreventsJoiningAnotherPersonsDelivery() {
        let (store, dir) = makeStore()
        defer { try? FileManager.default.removeItem(at: dir) }
        XCTAssertTrue(store.append(fixture()))
        XCTAssertTrue(store.recordResponse(personId: "person-2", deliveryId: "delivery-1", event: .saved, at: instant))
        XCTAssertNil(store.allCases().first?.response.saved)
        XCTAssertEqual(store.pendingObservations().count, 1)
    }

    func testInvalidProbabilityCannotBecomeAnEvalCase() {
        let (store, dir) = makeStore()
        defer { try? FileManager.default.removeItem(at: dir) }
        var row = fixture()
        row.stimulus.assignedProbability = 0
        XCTAssertFalse(store.append(row))
        row.stimulus.assignedProbability = 1.1
        XCTAssertFalse(store.append(row))
        XCTAssertTrue(store.allCases().isEmpty)
    }
    func testLateRealEventIsPreservedSeparatelyFromClosedWindowOutcome() {
        let (store, dir) = makeStore()
        defer { try? FileManager.default.removeItem(at: dir) }
        XCTAssertTrue(store.append(fixture()))
        store.closeObservationWindows(at: instant.addingTimeInterval(1800))
        XCTAssertTrue(store.recordResponse(personId: "person-1", deliveryId: "delivery-1", event: .saved, at: instant.addingTimeInterval(2000)))
        XCTAssertEqual(store.allCases().first?.response.saved, false)
        XCTAssertEqual(store.outsideWindowObservations().first?.event, .saved)
        XCTAssertEqual(store.outsideWindowObservations().first?.observedAt, instant.addingTimeInterval(2000))
    }

    func testLegacyPositiveIsNotChangedToFalseWhenWindowCloses() throws {
        let (_, dir) = makeStore()
        defer { try? FileManager.default.removeItem(at: dir) }
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let old = DecisionPointRecord(recordKind: "decision", personId: "p", deliveryId: "d",
            decisionPointAt: "2023-11-14T22:13:20Z", available: true, treatmentAssigned: "q029",
            assignedProbability: 1, messageId: "q029", policyVersion: "rule_v1", source: "onboarding_first_intervention",
            painPointIds: [], proximalOutcome: "responded", outcomeWindowSec: 1800)
        try JSONEncoder().encode(old).write(to: dir.appendingPathComponent("decision-points.jsonl"))
        let store = DecisionPointStore(directory: dir)
        store.closeObservationWindows(at: instant.addingTimeInterval(2000))
        XCTAssertEqual(store.allCases().first?.response.responded, true)
        XCTAssertNil(store.allCases().first?.response.respondedAt)
        XCTAssertEqual(DecisionPointStore(directory: dir).allCases().count, 1)
    }

    @MainActor
    func testRemoteSituationRejectsNamesRawBirthDatesAndUnmeasuredPermissionClaims() {
        var situation = fixture().situation
        situation.notificationPermission = "authorized"
        XCTAssertTrue(DecisionPointRecorder.isEnumeratedSituation(situation))
        situation.answerSnapshot["preferred_name"] = ["Private Name"]
        XCTAssertFalse(DecisionPointRecorder.isEnumeratedSituation(situation))
        situation.answerSnapshot.removeValue(forKey: "preferred_name")
        situation.answerSnapshot["birth_context"] = ["1980-01-01"]
        XCTAssertFalse(DecisionPointRecorder.isEnumeratedSituation(situation))
        situation.answerSnapshot["birth_context"] = ["date_provided"]
        situation.notificationPermission = "skipped"
        XCTAssertFalse(DecisionPointRecorder.isEnumeratedSituation(situation))
    }

}
