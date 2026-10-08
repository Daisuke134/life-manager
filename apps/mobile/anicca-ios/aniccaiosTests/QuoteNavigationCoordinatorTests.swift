import Foundation
import Testing
@testable import aniccaios

@MainActor
struct QuoteNavigationCoordinatorTests {

    @Test("Cold-start notification waits for quotes and follows the visible alert body")
    func coldStartUsesAlertBodyWhenQuoteIdDisagrees() {
        let suiteName = "QuoteNavigationCoordinatorTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        let storageKey = "pendingQuoteNavigation"
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let notificationHandler = QuoteNavigationCoordinator(defaults: defaults, storageKey: storageKey)
        notificationHandler.request(
            quoteID: "q001",
            alertBody: "I am exactly where I need to be in my journey."
        )

        let feedAfterColdStart = QuoteNavigationCoordinator(defaults: defaults, storageKey: storageKey)
        #expect(feedAfterColdStart.resolveQuote(in: []) == nil)
        #expect(feedAfterColdStart.pendingRequest?.quoteID == "q001")

        let quotes = [
            Quote(id: "q001", text: "I am committed to becoming who I am meant to be."),
            Quote(id: "q007", text: "I am exactly where I need to be in my journey."),
        ]
        #expect(feedAfterColdStart.resolveQuote(in: quotes) == quotes[1])
        #expect(feedAfterColdStart.pendingRequest == nil)
        #expect(defaults.data(forKey: storageKey) == nil)
    }

    @Test("An alert body absent from the catalog is shown instead of a conflicting quote ID")
    func unknownAlertBodyTakesPrecedenceOverConflictingQuoteID() {
        let suiteName = "QuoteNavigationCoordinatorTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let coordinator = QuoteNavigationCoordinator(defaults: defaults, storageKey: "pendingQuoteNavigation")
        coordinator.request(quoteID: "q001", alertBody: "A different affirmation not in this catalog.")

        let quotes = [Quote(id: "q001", text: "I am committed to becoming who I am meant to be.")]
        #expect(coordinator.resolveQuote(in: quotes) == Quote(
            id: "notification:q001",
            text: "A different affirmation not in this catalog."
        ))
        #expect(coordinator.pendingRequest == nil)
    }

    @Test("ID-only deep links still open the matching stable quote ID")
    func idOnlyDeepLinkKeepsExistingBehavior() {
        let suiteName = "QuoteNavigationCoordinatorTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let coordinator = QuoteNavigationCoordinator(defaults: defaults, storageKey: "pendingQuoteNavigation")
        coordinator.request(quoteID: "q007", alertBody: nil)

        let quotes = [
            Quote(id: "q001", text: "First affirmation."),
            Quote(id: "q007", text: "Exact deep-link destination."),
        ]
        #expect(coordinator.resolveQuote(in: quotes) == quotes[1])
        #expect(coordinator.pendingRequest == nil)
    }
}
