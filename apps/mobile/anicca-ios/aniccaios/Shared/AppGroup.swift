import Foundation
import OSLog

enum AppGroup {
    private static let logger = Logger(subsystem: "com.anicca.ios", category: "AppGroup")
    private static let candidateIdentifiers = [
        "group.ai.anicca.app.ios",
        "group.ai.anicca.app"
    ]

    private static let resolvedSuiteName: String = {
        for identifier in candidateIdentifiers {
            if FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: identifier) != nil {
                return identifier
            }
        }
        logger.error("App Group container not found; falling back to \(candidateIdentifiers[0], privacy: .public)")
        return candidateIdentifiers[0]
    }()

    private static let cachedDefaults: UserDefaults = {
        guard let defaults = UserDefaults(suiteName: resolvedSuiteName) else {
            fatalError("Unable to create UserDefaults for app group \(resolvedSuiteName)")
        }
        return defaults
    }()

    static var suiteName: String { resolvedSuiteName }
    static var userDefaults: UserDefaults { cachedDefaults }
}

