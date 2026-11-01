import XCTest
@testable import aniccaios

final class ReviewPromptPolicyTests: XCTestCase {

    private var calendar: Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(secondsFromGMT: 0)!
        return cal
    }

    private func date(_ y: Int, _ m: Int, _ d: Int) -> Date {
        calendar.date(from: DateComponents(year: y, month: m, day: d, hour: 12))!
    }

    private func eligible() -> ReviewPromptState {
        ReviewPromptState(
            isOnboardingComplete: true, launchCount: 3, distinctOpenDayCount: 2, saveCount: 3,
            lastPromptAt: nil, lastPromptVersion: nil, previousScreen: .other
        )
    }

    private func allowed(_ s: ReviewPromptState, version: String = "1.9.7", now: Date? = nil) -> Bool {
        ReviewPromptPolicy.shouldRequestReview(state: s, currentVersion: version, now: now ?? date(2026, 11, 2), calendar: calendar)
    }

    func test_true_whenAllThresholdsMet() { XCTAssertTrue(allowed(eligible())) }

    func test_false_beforeOnboardingComplete() {
        var s = eligible(); s.isOnboardingComplete = false
        XCTAssertFalse(allowed(s))
    }

    func test_false_withTwoLaunches() {
        var s = eligible(); s.launchCount = 2
        XCTAssertFalse(allowed(s))
    }

    func test_false_withOneOpenDay() {
        var s = eligible(); s.distinctOpenDayCount = 1
        XCTAssertFalse(allowed(s))
    }

    func test_false_withTwoSaves() {
        var s = eligible(); s.saveCount = 2
        XCTAssertFalse(allowed(s))
    }

    func test_false_afterPaywall() {
        var s = eligible(); s.previousScreen = .paywall
        XCTAssertFalse(allowed(s))
    }

    func test_false_afterNotificationPermission() {
        var s = eligible(); s.previousScreen = .notificationPermission
        XCTAssertFalse(allowed(s))
    }

    func test_false_afterError() {
        var s = eligible(); s.previousScreen = .error
        XCTAssertFalse(allowed(s))
    }

    func test_false_sameVersionAlreadyPrompted() {
        var s = eligible(); s.lastPromptVersion = "1.9.7"; s.lastPromptAt = date(2026, 1, 1)
        XCTAssertFalse(allowed(s, version: "1.9.7"))
    }

    func test_false_newVersionWithin120Days() {
        var s = eligible(); s.lastPromptVersion = "1.9.6"; s.lastPromptAt = date(2026, 10, 1)
        XCTAssertFalse(allowed(s, version: "1.9.7", now: date(2026, 11, 2)))
    }

    func test_true_newVersionAfter120Days() {
        var s = eligible(); s.lastPromptVersion = "1.9.6"; s.lastPromptAt = date(2026, 6, 1)
        XCTAssertTrue(allowed(s, version: "1.9.7", now: date(2026, 9, 29)))
    }

    func test_false_oneDayShortOf120() {
        var s = eligible(); s.lastPromptVersion = "1.9.6"; s.lastPromptAt = date(2026, 6, 1)
        XCTAssertFalse(allowed(s, version: "1.9.7", now: date(2026, 9, 28)))
    }

    func test_delayIs0_8Seconds() { XCTAssertEqual(ReviewPromptPolicy.delayAfterSave, 0.8) }

    func test_recordingOpenDay_isIdempotentPerDay() {
        var keys = ReviewPromptPolicy.recordingOpenDay(existingDayKeys: [], now: date(2026, 11, 2), calendar: calendar)
        keys = ReviewPromptPolicy.recordingOpenDay(existingDayKeys: keys, now: date(2026, 11, 2), calendar: calendar)
        XCTAssertEqual(keys.count, 1)
        keys = ReviewPromptPolicy.recordingOpenDay(existingDayKeys: keys, now: date(2026, 11, 3), calendar: calendar)
        XCTAssertEqual(keys, ["2026-11-02", "2026-11-03"])
    }
}
