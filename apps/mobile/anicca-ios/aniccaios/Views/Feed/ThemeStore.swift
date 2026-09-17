import SwiftUI
import Combine

/// One of 8 background themes shipped Day 1.
/// New themes are added by dropping a PNG into `Assets.xcassets/Themes/` and adding a case here.
enum ThemeID: String, CaseIterable, Codable, Identifiable {
    case silkDusk
    case sandWave
    case oceanSunset
    case midnightDusk
    case linenCream
    case sageMist
    case skyDawn
    case rosePetal

    var id: String { rawValue }

    /// Display label shown in the Theme picker.
    var displayName: String {
        switch self {
        case .silkDusk: return String(localized: "theme_silk_dusk")
        case .sandWave: return String(localized: "theme_sand_wave")
        case .oceanSunset: return String(localized: "theme_ocean_sunset")
        case .midnightDusk: return String(localized: "theme_midnight_dusk")
        case .linenCream: return String(localized: "theme_linen_cream")
        case .sageMist: return String(localized: "theme_sage_mist")
        case .skyDawn: return String(localized: "theme_sky_dawn")
        case .rosePetal: return String(localized: "theme_rose_petal")
        }
    }

    /// SwiftUI Image loaded from Assets.xcassets/Themes/<id>.imageset.
    var image: Image { Image("Themes/\(rawValue)") }
}

/// Owns the currently-selected background theme.
/// Persisted to UserDefaults; changes propagate to FeedRootView via @Published.
@MainActor
final class ThemeStore: ObservableObject {
    @Published var selected: ThemeID

    private static let storageKey = "anicca.theme"

    init() {
        if let raw = UserDefaults.standard.string(forKey: Self.storageKey),
           let id = ThemeID(rawValue: raw) {
            self.selected = id
        } else {
            self.selected = .sageMist
        }
    }

    func select(_ id: ThemeID) {
        selected = id
        UserDefaults.standard.set(id.rawValue, forKey: Self.storageKey)
    }

    var image: Image { selected.image }
}
