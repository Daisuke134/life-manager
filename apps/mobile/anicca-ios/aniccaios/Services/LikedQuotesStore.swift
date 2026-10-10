import Foundation
import Combine

/// UserDefaults-backed Set<String> of liked quote ids.
/// Used by ♡ button + Saved/Liked screens.
@MainActor
final class LikedQuotesStore: ObservableObject {
    @Published private(set) var likedIds: Set<String>

    private static let storageKey = "anicca.liked.ids"

    init() {
        let raw = UserDefaults.standard.array(forKey: Self.storageKey) as? [String] ?? []
        self.likedIds = Set(raw)
    }

    func isLiked(_ id: String) -> Bool { likedIds.contains(id) }

    /// Toggles like state. Returns `true` when the quote was newly favorited.
    @discardableResult
    func toggle(_ id: String) -> Bool {
        if likedIds.contains(id) {
            likedIds.remove(id)
            persist()
            return false
        } else {
            likedIds.insert(id)
            persist()
            return true
        }
    }

    private func persist() {
        UserDefaults.standard.set(Array(likedIds), forKey: Self.storageKey)
    }
}
