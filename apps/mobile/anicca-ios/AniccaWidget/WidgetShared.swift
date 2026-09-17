import Foundation

// MARK: - AppGroup (Widget copy — same logic as main app)

enum AppGroup {
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

// MARK: - NudgeWidgetDataStore (read-only for widget)

enum NudgeWidgetDataStore {
    private static let textsKey = "widget_nudge_texts"
    private static let strugglesKey = "widget_user_struggles"

    static func loadTexts() -> [String: [String]] {
        guard let data = AppGroup.userDefaults.data(forKey: textsKey),
              let texts = try? JSONDecoder().decode([String: [String]].self, from: data) else {
            return [:]
        }
        return texts
    }

    static func loadStruggles() -> [String] {
        AppGroup.userDefaults.stringArray(forKey: strugglesKey) ?? []
    }
}

// MARK: - ProblemType (icon only — mirror of main app's ProblemType)

enum ProblemType: String {
    case stayingUpLate = "staying_up_late"
    case cantWakeUp = "cant_wake_up"
    case selfLoathing = "self_loathing"
    case rumination = "rumination"
    case procrastination = "procrastination"
    case anxiety = "anxiety"
    case lying = "lying"
    case badMouthing = "bad_mouthing"
    case pornAddiction = "porn_addiction"
    case alcoholDependency = "alcohol_dependency"
    case anger = "anger"
    case obsessive = "obsessive"
    case loneliness = "loneliness"

    var icon: String {
        switch self {
        case .stayingUpLate: return "🌙"
        case .cantWakeUp: return "☀️"
        case .selfLoathing: return "🤍"
        case .rumination: return "💭"
        case .procrastination: return "⏰"
        case .anxiety: return "🌊"
        case .lying: return "🤥"
        case .badMouthing: return "💬"
        case .pornAddiction: return "🚫"
        case .alcoholDependency: return "🍺"
        case .anger: return "🔥"
        case .obsessive: return "🔄"
        case .loneliness: return "💙"
        }
    }
}
