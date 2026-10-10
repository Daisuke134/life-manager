import XCTest
@testable import aniccaios

final class ReviewPromptPolicyTests: XCTestCase {

    private var calendar: Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(secondsFromGMT: 0)!
        return cal
    }

    private func date(_ year: Int, _ month: Int, _ day: Int, hour: Int = 12) -> Date {
        calendar.date(from: DateComponents(year: year, month: month, day: day, hour: hour))!
    }

    // MARK: - shouldRequestReview

    func test_shouldRequest_false_onFirstLaunch_zeroDays() {
        XCTAssertFalse(
            ReviewPromptPolicy.shouldRequestReview(
                distinctOpenDayCount: 0,
                lastReviewRequestAt: nil,
                now: date(2026, 10, 9),
                calendar: calendar
            )
        )
    }

    func test_shouldRequest_false_onFirstLaunch_oneDay() {
        XCTAssertFalse(
            ReviewPromptPolicy.shouldRequestReview(
                distinctOpenDayCount: 1,
                lastReviewRequestAt: nil,
                now: date(2026, 10, 9),
                calendar: calendar
            )
        )
    }

    func test_shouldRequest_false_withTwoDistinctDays() {
        XCTAssertFalse(
            ReviewPromptPolicy.shouldRequestReview(
                distinctOpenDayCount: 2,
                lastReviewRequestAt: nil,
                now: date(2026, 10, 9),
                calendar: calendar
            )
        )
    }

    func test_shouldRequest_true_afterThreeDistinctDays_neverAsked() {
        XCTAssertTrue(
            ReviewPromptPolicy.shouldRequestReview(
                distinctOpenDayCount: 3,
                lastReviewRequestAt: nil,
                now: date(2026, 10, 9),
                calendar: calendar
            )
        )
    }

    func test_shouldRequest_false_within120DayCooldown() {
        let last = date(2026, 6, 12)
        let now = date(2026, 10, 9) // 119 days later
        XCTAssertFalse(
            ReviewPromptPolicy.shouldRequestReview(
                distinctOpenDayCount: 10,
                lastReviewRequestAt: last,
                now: now,
                calendar: calendar
            )
        )
    }

    func test_shouldRequest_true_after120DayCooldown() {
        let last = date(2026, 6, 11)
        let now = date(2026, 10, 9) // exactly 120 days later
        XCTAssertTrue(
            ReviewPromptPolicy.shouldRequestReview(
                distinctOpenDayCount: 5,
                lastReviewRequestAt: last,
                now: now,
                calendar: calendar
            )
        )
    }

    func test_shouldRequest_true_wellPastCooldown() {
        XCTAssertTrue(
            ReviewPromptPolicy.shouldRequestReview(
                distinctOpenDayCount: 3,
                lastReviewRequestAt: date(2025, 1, 1),
                now: date(2026, 10, 9),
                calendar: calendar
            )
        )
    }

    // MARK: - recordingOpenDay

    func test_recordingOpenDay_addsTodayOnce() {
        let day1 = date(2026, 10, 1)
        var days = ReviewPromptPolicy.recordingOpenDay(
            existingDayKeys: [],
            now: day1,
            calendar: calendar
        )
        XCTAssertEqual(days.count, 1)
        XCTAssertEqual(days, ["2026-10-01"])

        days = ReviewPromptPolicy.recordingOpenDay(
            existingDayKeys: days,
            now: date(2026, 10, 1, hour: 23),
            calendar: calendar
        )
        XCTAssertEqual(days.count, 1)

        days = ReviewPromptPolicy.recordingOpenDay(
            existingDayKeys: days,
            now: date(2026, 10, 2),
            calendar: calendar
        )
        XCTAssertEqual(days.count, 2)
        XCTAssertTrue(days.contains("2026-10-02"))
    }

    // MARK: - Coordinator integration (injected defaults)

    @MainActor
    func test_coordinator_requestsOnlyAfterThreeDaysAndValueMomentGate() {
        let suite = "ReviewPromptPolicyTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }

        let coordinator = ReviewPromptCoordinator(
            defaults: defaults,
            openDaysKey: "openDays",
            lastRequestKey: "lastRequest"
        )

        var requestCount = 0
        let request: () -> Void = { requestCount += 1 }

        coordinator.recordAppOpen(now: date(2026, 10, 1), calendar: calendar)
        XCTAssertFalse(coordinator.requestReviewIfAppropriate(
            now: date(2026, 10, 1),
            calendar: calendar,
            request: request
        ))

        coordinator.recordAppOpen(now: date(2026, 10, 2), calendar: calendar)
        XCTAssertFalse(coordinator.requestReviewIfAppropriate(
            now: date(2026, 10, 2),
            calendar: calendar,
            request: request
        ))

        coordinator.recordAppOpen(now: date(2026, 10, 3), calendar: calendar)
        XCTAssertTrue(coordinator.requestReviewIfAppropriate(
            now: date(2026, 10, 3),
            calendar: calendar,
            request: request
        ))
        XCTAssertEqual(requestCount, 1)

        // Same day / within cooldown: no second ask
        XCTAssertFalse(coordinator.requestReviewIfAppropriate(
            now: date(2026, 10, 4),
            calendar: calendar,
            request: request
        ))
        XCTAssertEqual(requestCount, 1)

        // After cooldown
        XCTAssertTrue(coordinator.requestReviewIfAppropriate(
            now: date(2027, 2, 1),
            calendar: calendar,
            request: request
        ))
        XCTAssertEqual(requestCount, 2)
    }
}
