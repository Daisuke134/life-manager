import Foundation

/// Resolves language-specific .lproj bundles from SPM's Bundle.module.
/// Used by CardRenderer to get correct localized text for each language.
enum LocalizationBundle {
    /// Load the .lproj bundle for the specified language.
    /// In SPM: uses Bundle.module (auto-generated when resources are declared).
    /// Fallback: Bundle.main (should not happen in CLI context).
    static func bundle(for language: String) -> Bundle {
        let langCode = language == "ja" ? "ja" : "en"
        #if SWIFT_PACKAGE
        guard let path = Bundle.module.path(forResource: langCode, ofType: "lproj"),
              let bundle = Bundle(path: path) else {
            return Bundle.module
        }
        return bundle
        #else
        return Bundle.main
        #endif
    }
}
