import Combine
import CryptoKit
import Foundation

struct QuoteNavigationRequest: Codable, Equatable {
    let quoteID: String?
    let alertBody: String?
    var deliveryId: String? = nil
}

@MainActor
final class QuoteNavigationCoordinator: ObservableObject {
    static let shared = QuoteNavigationCoordinator()

    @Published private(set) var pendingRequest: QuoteNavigationRequest?

    private let defaults: UserDefaults
    private let storageKey: String

    init(defaults: UserDefaults = .standard, storageKey: String = "com.anicca.pendingQuoteNavigation") {
        self.defaults = defaults
        self.storageKey = storageKey

        if let data = defaults.data(forKey: storageKey),
           let request = try? JSONDecoder().decode(QuoteNavigationRequest.self, from: data) {
            pendingRequest = request
        } else {
            defaults.removeObject(forKey: storageKey)
        }
    }

    func request(quoteID: String?, alertBody: String?, deliveryId: String? = nil) {
        let cleanedID = quoteID?.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanedBody = alertBody?.trimmingCharacters(in: .whitespacesAndNewlines)
        let request = QuoteNavigationRequest(
            quoteID: cleanedID?.isEmpty == false ? cleanedID : nil,
            alertBody: cleanedBody?.isEmpty == false ? cleanedBody : nil,
            deliveryId: deliveryId
        )
        guard request.quoteID != nil || request.alertBody != nil else { return }

        pendingRequest = request
        if let data = try? JSONEncoder().encode(request) {
            defaults.set(data, forKey: storageKey)
        }
    }

    func resolveQuote(in quotes: [Quote]) -> Quote? {
        guard let request = pendingRequest, !quotes.isEmpty else { return nil }

        if let alertBody = request.alertBody {
            let body = normalize(alertBody)
            let exactMatches = quotes.indices.filter { index in
                normalize(quotes[index].text) == body
            }
            if exactMatches.count == 1 {
                return finish(Quote(id: quotes[exactMatches[0]].id, text: alertBody))
            }

            let containingMatches = quotes.indices.filter { index in
                let text = normalize(quotes[index].text)
                return !text.isEmpty && body.contains(text)
            }
            if containingMatches.count == 1 {
                return finish(Quote(id: quotes[containingMatches[0]].id, text: alertBody))
            }

            // The tapped alert body is the visible source of truth. If this app
            // version has no matching catalog entry, show that exact body instead
            // of navigating to a different quote with a stale/mismatched ID.
            let contentID = SHA256.hash(data: Data(alertBody.utf8))
                .map { String(format: "%02x", $0) }.joined()
            return finish(Quote(id: "notification:\(contentID)", text: alertBody))
        }

        guard let quoteID = request.quoteID,
              let quote = quotes.first(where: { $0.id == quoteID }) else {
            return finish(nil)
        }
        return finish(quote)
    }

    func feedDestination(for quote: Quote, in feed: [Quote]) -> (quotes: [Quote], index: Int) {
        var updatedFeed = feed
        if let index = updatedFeed.firstIndex(where: { $0.id == quote.id }) {
            updatedFeed[index] = quote
            return (updatedFeed, index)
        }
        updatedFeed.append(quote)
        return (updatedFeed, updatedFeed.count - 1)
    }

    private func finish(_ quote: Quote?) -> Quote? {
        pendingRequest = nil
        defaults.removeObject(forKey: storageKey)
        return quote
    }

    private func normalize(_ text: String) -> String {
        text.split(whereSeparator: { $0.isWhitespace })
            .map(String.init)
            .joined(separator: " ")
            .folding(options: [.caseInsensitive], locale: .current)
    }
}
