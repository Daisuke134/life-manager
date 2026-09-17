// Config.swift - runtime values are injected by private build settings or the environment.
import Foundation

enum Config {
    private static func value(_ key: String) -> String {
        if let environment = ProcessInfo.processInfo.environment[key], !environment.isEmpty {
            return environment
        }
        return Bundle.main.object(forInfoDictionaryKey: key) as? String ?? ""
    }

    static var APPLE_API_ISSUER_ID: String { value("APPLE_API_ISSUER_ID") }
    static var APPLE_API_KEY_ID: String { value("APPLE_API_KEY_ID") }
    static var EXPO_PUBLIC_PROJECT_ID: String { value("EXPO_PUBLIC_PROJECT_ID") }
    static var EXPO_PUBLIC_REVENUECAT_IOS_API_KEY: String { value("EXPO_PUBLIC_REVENUECAT_IOS_API_KEY") }
    static var EXPO_PUBLIC_REVENUECAT_TEST_API_KEY: String { value("EXPO_PUBLIC_REVENUECAT_TEST_API_KEY") }
    static var EXPO_PUBLIC_RORK_API_BASE_URL: String { value("EXPO_PUBLIC_RORK_API_BASE_URL") }
    static var EXPO_PUBLIC_TEAM_ID: String { value("EXPO_PUBLIC_TEAM_ID") }
    static var EXPO_PUBLIC_TOOLKIT_URL: String { value("EXPO_PUBLIC_TOOLKIT_URL") }

    static var allValues: [String: String] {
        [
            "APPLE_API_ISSUER_ID": APPLE_API_ISSUER_ID,
            "APPLE_API_KEY_ID": APPLE_API_KEY_ID,
            "EXPO_PUBLIC_PROJECT_ID": EXPO_PUBLIC_PROJECT_ID,
            "EXPO_PUBLIC_REVENUECAT_IOS_API_KEY": EXPO_PUBLIC_REVENUECAT_IOS_API_KEY,
            "EXPO_PUBLIC_REVENUECAT_TEST_API_KEY": EXPO_PUBLIC_REVENUECAT_TEST_API_KEY,
            "EXPO_PUBLIC_RORK_API_BASE_URL": EXPO_PUBLIC_RORK_API_BASE_URL,
            "EXPO_PUBLIC_TEAM_ID": EXPO_PUBLIC_TEAM_ID,
            "EXPO_PUBLIC_TOOLKIT_URL": EXPO_PUBLIC_TOOLKIT_URL,
        ]
    }
}
