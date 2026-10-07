import Combine
import Foundation

struct QuoteNavigationRequest: Codable, Equatable {
    let quoteID: String?
    let alertBody: String?
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

    func request(quoteID: String?, alertBody: String?) {
        let cleanedID = quoteID?.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanedBody = alertBody?.trimmingCharacters(in: .whitespacesAndNewlines)
        let request = QuoteNavigationRequest(
            quoteID: cleanedID?.isEmpty == false ? cleanedID : nil,
            alertBody: cleanedBody?.isEmpty == false ? cleanedBody : nil
        )
        guard request.quoteID != nil || request.alertBody != nil else { return }

        pendingRequest = request
        if let data = try? JSONEncoder().encode(request) {
            defaults.set(data, forKey: storageKey)
        }
    }

    func resolveIndex(in quotes: [Quote]) -> Int? {
        guard let request = pendingRequest, !quotes.isEmpty else { return nil }

        if let alertBody = request.alertBody {
            let body = normalize(alertBody)
            let exactMatches = quotes.indices.filter { index in
                normalize(quotes[index].text) == body
            }
            if exactMatches.count == 1 {
                return finish(exactMatches[0])
            }

            let containingMatches = quotes.indices.filter { index in
                let text = normalize(quotes[index].text)
                return !text.isEmpty && body.contains(text)
            }
            if containingMatches.count == 1 {
                return finish(containingMatches[0])
            }
        }

        guard let quoteID = request.quoteID,
              let index = quotes.firstIndex(where: { $0.id == quoteID }) else {
            return finish(nil)
        }
        return finish(index)
    }

    private func finish(_ index: Int?) -> Int? {
        pendingRequest = nil
        defaults.removeObject(forKey: storageKey)
        return index
    }

    private func normalize(_ text: String) -> String {
        text.split(whereSeparator: { $0.isWhitespace })
            .map(String.init)
            .joined(separator: " ")
            .folding(options: [.caseInsensitive], locale: .current)
    }
}
