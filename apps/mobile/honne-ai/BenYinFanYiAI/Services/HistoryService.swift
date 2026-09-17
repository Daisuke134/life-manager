import SwiftUI

@Observable
@MainActor
class HistoryService {
    var results: [TranslationResult] = []

    private let storageKey = "translation_history"

    init() {
        loadHistory()
    }

    func addResult(_ result: TranslationResult) {
        results.insert(result, at: 0)
        if results.count > 100 {
            results = Array(results.prefix(100))
        }
        saveHistory()
    }

    func removeResult(at offsets: IndexSet) {
        results.remove(atOffsets: offsets)
        saveHistory()
    }

    func clearAll() {
        results.removeAll()
        saveHistory()
    }

    private func saveHistory() {
        guard let data = try? JSONEncoder().encode(results) else { return }
        UserDefaults.standard.set(data, forKey: storageKey)
    }

    private func loadHistory() {
        guard let data = UserDefaults.standard.data(forKey: storageKey),
              let saved = try? JSONDecoder().decode([TranslationResult].self, from: data) else { return }
        results = saved
    }
}
