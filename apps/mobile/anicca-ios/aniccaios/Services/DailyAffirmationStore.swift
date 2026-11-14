import Foundation

/// Keeps one affirmation for the current local day, including the exact first intervention.
@MainActor
final class DailyAffirmationStore {
    static let shared = DailyAffirmationStore()

    struct Presentation: Equatable {
        let quote: Quote
        let deliveryId: String?
    }

    private struct Entry: Codable {
        let quote: Quote
        let language: String
        let selectedAt: Date
        let deliveryId: String?
    }

    private let defaults: UserDefaults
    private let storageKey = "anicca.daily.affirmation"

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    func clear() {
        defaults.removeObject(forKey: storageKey)
    }

    func seed(_ quote: Quote, language: String, deliveryId: String? = nil, now: Date = Date()) {
        let entry = Entry(quote: quote, language: language, selectedAt: now, deliveryId: deliveryId)
        if let data = try? JSONEncoder().encode(entry) {
            defaults.set(data, forKey: storageKey)
        }
    }

    func todayAffirmation(
        language: String,
        now: Date = Date(),
        calendar: Calendar = .current,
        select: () -> Presentation?
    ) -> Presentation? {
        if let data = defaults.data(forKey: storageKey),
           let entry = try? JSONDecoder().decode(Entry.self, from: data),
           entry.language == language,
           calendar.isDate(entry.selectedAt, inSameDayAs: now) {
            return Presentation(quote: entry.quote, deliveryId: entry.deliveryId)
        }
        guard let presentation = select() else { return nil }
        seed(presentation.quote, language: language, deliveryId: presentation.deliveryId, now: now)
        return presentation
    }
}
