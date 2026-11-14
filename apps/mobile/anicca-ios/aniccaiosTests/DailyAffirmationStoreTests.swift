import XCTest
@testable import aniccaios

@MainActor
final class DailyAffirmationStoreTests: XCTestCase {
    func testFirstInterventionSurvivesRelaunchWithoutReselection() {
        withDefaults { defaults in
            let date = Date(timeIntervalSince1970: 1_800_000_000)
            let intervention = Quote(id: "q013", text: "I can be kind to myself.")
            DailyAffirmationStore(defaults: defaults).seed(intervention, language: "en", deliveryId: "first-intervention", now: date)
            var selections = 0
            let restored = DailyAffirmationStore(defaults: defaults)
            let result = restored.todayAffirmation(language: "en", now: date) {
                selections += 1
                return .init(quote: Quote(id: "q014", text: "A different quote."), deliveryId: "different")
            }
            XCTAssertEqual(result?.quote, intervention)
            XCTAssertEqual(result?.deliveryId, "first-intervention")
            XCTAssertEqual(selections, 0)
        }
    }

    func testNewDaySelectsOnceAndLanguageChangeRefreshes() {
        withDefaults { defaults in
            var calendar = Calendar(identifier: .gregorian)
            calendar.timeZone = TimeZone(secondsFromGMT: 0)!
            let date = Date(timeIntervalSince1970: 1_800_000_000)
            let nextDay = calendar.date(byAdding: .day, value: 1, to: date)!
            let first = Quote(id: "q013", text: "First")
            let second = Quote(id: "q014", text: "Second")
            let translated = Quote(id: "q014", text: "二つ目")
            let store = DailyAffirmationStore(defaults: defaults)
            store.seed(first, language: "en", now: date)
            var selections = 0
            XCTAssertEqual(store.todayAffirmation(language: "en", now: nextDay, calendar: calendar) {
                selections += 1
                return .init(quote: second, deliveryId: "new-day")
            }?.quote, second)
            XCTAssertEqual(store.todayAffirmation(language: "en", now: nextDay, calendar: calendar) {
                selections += 1
                return .init(quote: first, deliveryId: "wrong")
            }?.deliveryId, "new-day")
            XCTAssertEqual(selections, 1)
            XCTAssertEqual(store.todayAffirmation(language: "ja", now: nextDay, calendar: calendar) { .init(quote: translated, deliveryId: "translated") }?.quote, translated)
        }
    }

    func testNotificationReplacesTodayAndSurvivesRelaunch() {
        withDefaults { defaults in
            let date = Date(timeIntervalSince1970: 1_800_000_000)
            let store = DailyAffirmationStore(defaults: defaults)
            store.seed(Quote(id: "q013", text: "Daily words"), language: "en", now: date)
            let notification = Quote(id: "notification:unknown", text: "The exact words I tapped.")
            store.seed(notification, language: "en", deliveryId: "tapped-notification", now: date)
            let restored = DailyAffirmationStore(defaults: defaults).todayAffirmation(language: "en", now: date) { nil }
            XCTAssertEqual(restored?.quote, notification)
            XCTAssertEqual(restored?.deliveryId, "tapped-notification")
        }
    }

    func testClearingForAnotherPersonDoesNotReuseThePreviousPersonsAffirmation() {
        withDefaults { defaults in
            let date = Date(timeIntervalSince1970: 1_800_000_000)
            let store = DailyAffirmationStore(defaults: defaults)
            store.seed(Quote(id: "q013", text: "Previous person"), language: "en", now: date)
            store.clear()
            let next = Quote(id: "q014", text: "Next person")
            var selections = 0
            let result = DailyAffirmationStore(defaults: defaults).todayAffirmation(language: "en", now: date) {
                selections += 1
                return .init(quote: next, deliveryId: nil)
            }
            XCTAssertEqual(result?.quote, next)
            XCTAssertEqual(selections, 1)
        }
    }

    func testSavedQuoteKeepsItsThemeAndLegacyLikesStillLoad() {
        withDefaults { defaults in
            defaults.set(["q013"], forKey: "anicca.liked.ids")
            let catalogQuote = Quote(id: "q013", text: "Legacy favorite")
            let savedQuote = Quote(id: "q014", text: "Saved on sand")
            let store = LikedQuotesStore(defaults: defaults)
            XCTAssertEqual(store.savedQuotes(in: [catalogQuote]), [catalogQuote])
            XCTAssertEqual(store.themeID(for: catalogQuote.id), "sageMist")
            XCTAssertTrue(store.toggle(savedQuote, themeID: "sandWave"))
            defaults.set("midnightDusk", forKey: "anicca.theme")
            let restored = LikedQuotesStore(defaults: defaults)
            XCTAssertEqual(restored.themeID(for: savedQuote.id), "sandWave")
            XCTAssertTrue(restored.savedQuotes(in: []).contains(savedQuote))
            XCTAssertFalse(restored.toggle(savedQuote))
            XCTAssertFalse(LikedQuotesStore(defaults: defaults).isLiked(savedQuote.id))
        }
    }

    func testCachedHomePresentationDoesNotAdoptNewerDeliveryOfTheSameMessage() {
        withDefaults { defaults in
            let date = Date(timeIntervalSince1970: 1_800_000_000)
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: directory) }
            let journal = DecisionPointStore(directory: directory)
            let quote = Quote(id: "q021", text: "The same words")
            let home = ManagerBenchCase(personId: "p1", deliveryId: "home", decisionPointAt: date, source: "daily_home", outcomeWindowSec: 1800,
                situation: .init(answerSnapshot: [:], answerVersion: 4, scheduledTimeBand: "morning", weekday: "monday", notificationPermission: "authorized"),
                stimulus: .init(messageId: quote.id, category: "calm", tags: [], scheduledAt: date, treatmentAssigned: quote.id, assignedProbability: 1, policyVersion: "test"))
            XCTAssertTrue(journal.append(home))
            DailyAffirmationStore(defaults: defaults).seed(quote, language: "en", deliveryId: "home", now: date)
            XCTAssertTrue(journal.recordResponse(personId: "p1", deliveryId: "newer-notification", event: .notificationDelivered, at: date.addingTimeInterval(300), messageId: quote.id))
            let restored = DailyAffirmationStore(defaults: defaults).todayAffirmation(language: "en", now: date.addingTimeInterval(600)) { nil }
            XCTAssertEqual(restored?.deliveryId, "home")
            if let originalDelivery = restored?.deliveryId {
                XCTAssertTrue(journal.recordResponse(personId: "p1", deliveryId: originalDelivery, event: .saved, at: date.addingTimeInterval(600), messageId: quote.id))
            }
            XCTAssertEqual(journal.allCases().first?.response.saved, true)
            XCTAssertFalse(journal.pendingObservations().contains { $0.deliveryId == "newer-notification" && $0.event == .saved })
        }
    }

    func testLegacyCacheWithoutDeliveryIDRestoresUnknownOrigin() {
        struct LegacyEntry: Encodable { let quote: Quote; let language: String; let selectedAt: Date }
        withDefaults { defaults in
            let date = Date(timeIntervalSince1970: 1_800_000_000)
            let quote = Quote(id: "q021", text: "Legacy words")
            let data = try? JSONEncoder().encode(LegacyEntry(quote: quote, language: "en", selectedAt: date))
            defaults.set(data, forKey: "anicca.daily.affirmation")
            let restored = DailyAffirmationStore(defaults: defaults).todayAffirmation(language: "en", now: date) { nil }
            XCTAssertEqual(restored?.quote, quote)
            XCTAssertNil(restored?.deliveryId)
        }
    }

    private func withDefaults(_ body: (UserDefaults) -> Void) {
        let suite = "DailyAffirmationStoreTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        body(defaults)
    }
}
