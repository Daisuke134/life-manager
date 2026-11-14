import Foundation

/// The conditioning record. Raw onboarding answers are its source material;
/// neither a display name nor a birth date crosses this boundary.
struct SyntheticUser: Codable, Equatable {
    static let currentSchemaVersion = 2

    enum InterventionEvent: String, Codable {
        case assigned
        case notificationDelivered = "notification_delivered"
        case notificationOpened = "notification_opened"
        case appOpened = "app_opened"
        case responded, skipped, saved, shared
    }

    struct Intervention: Codable, Equatable {
        let deliveryId: String
        let messageId: String?
        let event: InterventionEvent
        let observedAt: Date
    }

    /// The old feed retained categories and an ordered recent-ID list, not
    /// observation timestamps. Keep those signals without inventing exposures.
    struct LegacySignals: Codable, Equatable {
        let goalCategoryIDs: [String]
        let problemCategoryIDs: [String]
        let likedCategoryIDs: [String]
        let recentMessageIDs: [String]

        init(goals: [String], problems: [String], likedIDs: [String], recentIDs: [String]) {
            let quotes = QuoteProvider.shared.all(preferredLanguage: .en)
            let categories = Set(quotes.map(\.categoryID))
            let knownIDs = Set(quotes.map(\.id))
            goalCategoryIDs = Array(Set(goals.map { QuoteProvider.goalCategories[$0] ?? $0 }).intersection(categories)).sorted()
            problemCategoryIDs = Array(Set(problems.flatMap { QuoteProvider.problemCategories[$0] ?? [] }).intersection(categories)).sorted()
            likedCategoryIDs = Array(Set(likedIDs.filter { knownIDs.contains($0) }.map { Quote(id: $0, text: "").categoryID })).sorted()
            recentMessageIDs = Array(recentIDs.filter { knownIDs.contains($0) }.suffix(20))
        }

        var preferredCategories: Set<String> { Set(goalCategoryIDs + problemCategoryIDs + likedCategoryIDs) }
    }

    let schemaVersion: Int
    let personId: String
    let attributes: [String: [String]]
    let initialState: [String: [String]]
    let beliefThemes: [String]
    let triggerContext: [String: [String]]
    let receptivityWindows: [String: [String]]
    let quietHours: [String]
    let motivation: [String: [String]]
    let preferences: [String: [String]]
    let hasAdaptiveAnswers: Bool
    let updatedAt: Date
    let legacySignals: LegacySignals?
    private(set) var interventionHistory: [Intervention]

    init(profile: PersonalizationProfile, personId: String, history: [Intervention] = [], legacySignals: LegacySignals? = nil, now: Date = Date()) {
        let values = profile.answerSnapshot(now: now).values
        func axes(_ keys: [String]) -> [String: [String]] {
            Dictionary(uniqueKeysWithValues: keys.map { ($0, values[$0] ?? ["unknown"]) })
        }
        schemaVersion = Self.currentSchemaVersion
        self.personId = personId
        attributes = axes(["age_band", "birth_context", "life_context"])
        initialState = axes(["mood_baseline"])
        beliefThemes = values["belief_themes"] ?? ["unknown"]
        triggerContext = axes(["pain_points", "struggle_frequency", "stress_trigger", "anxiety_target",
                               "self_criticism", "avoidance_task", "sleep_reason"])
        receptivityWindows = axes(["routine_anchors", "bedtime", "wake_time", "reminder_slots", "daily_frequency"])
        quietHours = values["quiet_hours"] ?? ["unknown"]
        motivation = axes(["desired_state", "start_reason"])
        var preferences = axes(["tone", "prior_attempts", "prior_helpfulness", "notification_permission"])
        let hasCalendarContext = profile.answers.birthDate != nil || !profile.answers.ids(for: .birthContext).isEmpty
        preferences["birthday_season"] = [hasCalendarContext
            ? (profile.answers.isBirthdaySeason(now: now) ? "active" : "inactive") : "unknown"]
        self.preferences = preferences
        hasAdaptiveAnswers = profile.adaptiveAnswers != nil
        updatedAt = now
        self.legacySignals = legacySignals
        interventionHistory = history
    }

    var answerSnapshot: OnboardingAnswerSnapshot {
        var values: [String: [String]] = [:]
        for group in [attributes, initialState, triggerContext, receptivityWindows, motivation, preferences] {
            values.merge(group) { _, new in new }
        }
        values["belief_themes"] = beliefThemes
        values["quiet_hours"] = quietHours
        if let legacySignals {
            values["legacy_goal_categories"] = legacySignals.goalCategoryIDs
            values["legacy_problem_categories"] = legacySignals.problemCategoryIDs
            values["legacy_liked_categories"] = legacySignals.likedCategoryIDs
            values["legacy_recent_message_ids"] = legacySignals.recentMessageIDs
        }
        return OnboardingAnswerSnapshot(version: 4, values: values)
    }

    var hasAnswers: Bool { conditioningProfile.hasAnswers }

    /// A projection of this record's IDs for the existing pure rules. It cannot
    /// read the material UserProfile or recover a name/birth date.
    var conditioningProfile: PersonalizationProfile {
        let values = answerSnapshot.values
        let desired = values["desired_state"]?.first
        let frequency = values["struggle_frequency"]?.first
        let validPain = ["stress", "anxiety", "self_doubt", "procrastination", "sleep"]
        let slots = PersonalizationRules.presetSlots.filter { slot in
            (values["reminder_slots"] ?? []).contains("slot_\(slot.hour)_\(slot.minute)")
        }
        var profile = PersonalizationProfile(
            desiredState: desired == "unknown" ? nil : desired,
            painPointIds: (values["pain_points"] ?? []).filter { validPain.contains($0) },
            struggleFrequency: frequency == "unknown" ? nil : frequency,
            nudgeSlots: slots,
            dailyFrequency: ["one": 1, "two": 2, "three": 3][values["daily_frequency"]?.first ?? ""] ?? 1,
            updatedAt: updatedAt)
        if hasAdaptiveAnswers { profile.adaptiveAnswers = AdaptiveAnswers(values: values) }
        return profile
    }

    var shownTimestamps: [String: Date] {
        var result: [String: Date] = [:]
        for observation in interventionHistory {
            guard observation.event == .assigned || observation.event == .notificationDelivered else { continue }
            guard let id = observation.messageId else { continue }
            if result[id].map({ $0 >= observation.observedAt }) != true { result[id] = observation.observedAt }
        }
        return result
    }

    mutating func recordIntervention(messageId: String?, deliveryId: String, event: String, at: Date) {
        let aliases: [String: InterventionEvent] = ["decision": .assigned, "selected": .assigned,
            "delivered": .notificationDelivered, "opened": .notificationOpened]
        guard let kind = InterventionEvent(rawValue: event) ?? aliases[event] else { return }
        let knownMessageId = messageId.flatMap { QuoteProvider.shared.byId($0, preferredLanguage: .en) == nil ? nil : $0 }
        let observation = Intervention(deliveryId: deliveryId, messageId: knownMessageId, event: kind, observedAt: at)
        if let index = interventionHistory.firstIndex(where: { $0.deliveryId == deliveryId && $0.event == kind }) {
            if at < interventionHistory[index].observedAt { interventionHistory[index] = observation }
        } else { interventionHistory.append(observation) }
    }

    func deliveryPayload(timezoneIdentifier: String) -> [String: Any] {
        let profile = conditioningProfile
        let slots = PersonalizationRules.effectiveSlots(user: self)
        return [
            "desiredState": profile.desiredState ?? "",
            "painPointIds": profile.painPointIds,
            "struggleFrequency": profile.struggleFrequency ?? "",
            "nudgeSlots": slots.map { $0.label },
            "dailyFrequency": slots.count,
            "answerIds": answerSnapshot.values,
            "answerVersion": answerSnapshot.version,
            "timezone": timezoneIdentifier,
            "schemaVersion": 3
        ]
    }
}

/// Uses the existing device pseudonym so the synthetic record and eval cases
/// refer to the same person without an account ID.
final class SyntheticUserStore {
    private let defaults: UserDefaults
    private let recordKey = "com.anicca.syntheticUser"
    private let personIdKey = "com.anicca.decisionPersonId"

    init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    var personId: String {
        if let existing = defaults.string(forKey: personIdKey) { return existing }
        let created = UUID().uuidString
        defaults.set(created, forKey: personIdKey)
        return created
    }

    func load() -> SyntheticUser? {
        guard let data = defaults.data(forKey: recordKey) else { return nil }
        guard let user = try? JSONDecoder().decode(SyntheticUser.self, from: data),
              (1...SyntheticUser.currentSchemaVersion).contains(user.schemaVersion) else { return nil }
        return user
    }

    @discardableResult
    func refresh(profile: PersonalizationProfile, observedHistory: [SyntheticUser.Intervention] = [], legacySignals: SyntheticUser.LegacySignals? = nil, now: Date = Date()) -> SyntheticUser {
        let currentPersonId = personId
        let previous = load()
        let history = previous?.personId == currentPersonId ? previous?.interventionHistory ?? [] : []
        var user = SyntheticUser(profile: profile, personId: currentPersonId, history: history,
                                 legacySignals: legacySignals ?? (previous?.personId == currentPersonId ? previous?.legacySignals : nil), now: now)
        for observation in observedHistory {
            user.recordIntervention(messageId: observation.messageId, deliveryId: observation.deliveryId,
                                    event: observation.event.rawValue, at: observation.observedAt)
        }
        save(user)
        return user
    }

    func save(_ user: SyntheticUser) {
        guard let data = try? JSONEncoder().encode(user) else { return }
        defaults.set(data, forKey: recordKey)
    }

    func clear() {
        defaults.removeObject(forKey: recordKey)
        defaults.removeObject(forKey: personIdKey)
    }
}

extension PersonalizationRules {
    static func effectiveSlots(user: SyntheticUser) -> [NudgeSlot] {
        effectiveSlots(profile: user.conditioningProfile)
    }

    static func availableSlots(user: SyntheticUser) -> [NudgeSlot] {
        availableSlots(profile: user.conditioningProfile)
    }

    static func initialSlots(user: SyntheticUser, frequency: Int) -> [NudgeSlot] {
        initialSlots(profile: user.conditioningProfile, frequency: frequency)
    }
}
