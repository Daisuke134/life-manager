import Foundation
import WidgetKit

enum NudgeWidgetDataStore {
    private static let textsKey = "widget_nudge_texts"
    private static let strugglesKey = "widget_user_struggles"

    static func sync(struggles: [String]) {
        let defaults = AppGroup.userDefaults
        defaults.set(struggles, forKey: strugglesKey)

        var allTexts: [String: [String]] = [:]
        for struggle in struggles {
            guard let problem = ProblemType(rawValue: struggle) else { continue }
            var texts: [String] = []
            for i in 1...60 {
                let key = "nudge_\(problem.rawValue)_notification_\(i)"
                let text = NSLocalizedString(key, comment: "")
                if text != key { texts.append(text) }
            }
            allTexts[struggle] = texts
        }

        if let data = try? JSONEncoder().encode(allTexts) {
            defaults.set(data, forKey: textsKey)
        }

        WidgetCenter.shared.reloadAllTimelines()
    }

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
