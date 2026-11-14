import Foundation

/// Onboarding answer material used to build the on-device SyntheticUser
/// conditioning record. The questions are defined in
/// `files/onboarding-answer-change-mapping-2026-11-14.md` (anicca-ops).
///
/// Every answer maps to a concrete change (affirmation selection, notification
/// schedule, first intervention). The free-text name stays on device only:
/// it is never sent to analytics or the profile sync payload.
struct PersonalizationProfile: Codable, Equatable {
    /// Trimmed display name. `nil` when the user left it blank.
    /// On-device rendering only (mapping rule 4).
    var preferredName: String?

    /// One of: calm / confidence / focus / self_love.
    var desiredState: String?

    /// Subset of: stress / anxiety / self_doubt / procrastination / sleep.
    var painPointIds: [String]

    /// One of: rarely / weekly / daily / many_times_daily.
    var struggleFrequency: String?

    /// User-selected notification wall-clock times (1...3 used slots).
    var nudgeSlots: [NudgeSlot]

    /// User-selected notifications per day (1...3, free cap 3).
    var dailyFrequency: Int

    /// Timezone the slots were chosen in; slots stay wall-clock across DST.
    var timezoneIdentifier: String

    var adaptiveAnswers: AdaptiveAnswers?

    var schemaVersion: Int
    var updatedAt: Date

    init(
        preferredName: String? = nil,
        desiredState: String? = nil,
        painPointIds: [String] = [],
        struggleFrequency: String? = nil,
        nudgeSlots: [NudgeSlot] = [],
        dailyFrequency: Int = 1,
        timezoneIdentifier: String = TimeZone.current.identifier,
        schemaVersion: Int = 2,
        updatedAt: Date = Date()
    ) {
        self.adaptiveAnswers = nil
        self.preferredName = preferredName
        self.desiredState = desiredState
        self.painPointIds = painPointIds
        self.struggleFrequency = struggleFrequency
        self.nudgeSlots = nudgeSlots
        self.dailyFrequency = dailyFrequency
        self.timezoneIdentifier = timezoneIdentifier
        self.schemaVersion = schemaVersion
        self.updatedAt = updatedAt
    }

    /// True once the user answered at least the desired-state question, i.e.
    /// the selector has something personal to work with.
    var hasAnswers: Bool {
        desiredState != nil || !painPointIds.isEmpty || struggleFrequency != nil
    }
}

/// A wall-clock notification time chosen by the user.
struct NudgeSlot: Codable, Equatable, Hashable, Comparable {
    var hour: Int
    var minute: Int

    static func < (lhs: NudgeSlot, rhs: NudgeSlot) -> Bool {
        (lhs.hour, lhs.minute) < (rhs.hour, rhs.minute)
    }

    var label: String {
        String(format: "%02d:%02d", hour, minute)
    }
}

/// Pure schedule + category rules from the answer→change mapping.
/// Kept free of UI and storage so the mapping is unit-testable.
enum PersonalizationRules {
    // MARK: - Notification schedule

    /// Selectable preset slots offered in onboarding (morning / midday /
    /// evening / night). The deployed sender's Pro times are reused so the
    /// choices stay inside the times the delivery stack already uses.
    static let presetSlots: [NudgeSlot] = [
        NudgeSlot(hour: 8, minute: 0),
        NudgeSlot(hour: 12, minute: 30),
        NudgeSlot(hour: 17, minute: 30),
        NudgeSlot(hour: 21, minute: 30),
    ]

    static let freeFrequencyCap = 3

    /// Initial daily-frequency proposal from the struggle-frequency answer
    /// (mapping: rarely/weekly → 1, daily → 2, many-times-daily → 3).
    /// The user's explicit choice always overrides this proposal.
    static func proposedFrequency(struggleFrequency: String?) -> Int {
        switch struggleFrequency {
        case "daily": return 2
        case "many_times_daily": return 3
        default: return 1
        }
    }

    /// Initial slot proposal: the first N presets, except that a `sleep`
    /// pain point shifts the proposal to the evening end of the day
    /// (mapping: sleep changes only the un-chosen default, never a choice).
    static func proposedSlots(painPointIds: [String], frequency: Int) -> [NudgeSlot] {
        let count = min(max(frequency, 1), presetSlots.count)
        if painPointIds.contains("sleep") {
            return Array(presetSlots.suffix(count)).sorted()
        }
        return Array(presetSlots.prefix(count))
    }

    /// A schedule is usable only when the frequency does not exceed the
    /// number of chosen slots (mapping: never silently add slots; ask the
    /// user to choose more instead).
    static func isValidSchedule(slots: [NudgeSlot], frequency: Int) -> Bool {
        guard (1...freeFrequencyCap).contains(frequency) else { return false }
        guard !slots.isEmpty, slots.count <= presetSlots.count else { return false }
        guard Set(slots).count == slots.count else { return false }
        return frequency <= slots.count
    }

    /// Message intensity from the struggle-frequency answer
    /// (mapping: rarely/weekly → gentle, daily/many-times-daily → supportive).
    static func intensity(struggleFrequency: String?) -> String {
        switch struggleFrequency {
        case "daily", "many_times_daily": return "supportive"
        default: return "gentle"
        }
    }

    // MARK: - Affirmation categories
    //
    // The mapping names abstract categories (stress_relief, grounding,
    // self_trust, small_action, rest, focus). The app's quote pool uses
    // concrete category IDs (see QuoteProvider / SupplementalAffirmations),
    // so the translation is fixed here, in one place:
    //   focus        -> presence   (the pool's focus category; the legacy
    //                              goal map already used focus_more -> presence)
    //   stress_relief -> resilience + calm
    //   grounding     -> presence (+ calm)
    //   self_trust    -> confidence (+ self_love)
    //   small_action  -> growth
    //   rest          -> rest

    static func primaryCategory(desiredState: String?) -> String? {
        switch desiredState {
        case "calm": return "calm"
        case "confidence": return "confidence"
        case "focus": return "presence"
        case "self_love": return "self_love"
        default: return nil
        }
    }

    static func boostCategories(painPointId: String) -> [String] {
        switch painPointId {
        case "stress": return ["resilience", "calm"]
        case "anxiety": return ["presence", "calm"]
        case "self_doubt": return ["confidence", "self_love"]
        case "procrastination": return ["growth"]
        case "sleep": return ["rest"]
        default: return []
        }
    }

    /// Bridge into the legacy ProblemType taxonomy used by the problem-nudge
    /// system and the feed's `problems` input. Only true counterparts are
    /// bridged; `stress` and `sleep` have no ProblemType counterpart and are
    /// intentionally not approximated.
    static func problemTypeBridge(painPointId: String) -> String? {
        switch painPointId {
        case "anxiety": return "anxiety"
        case "procrastination": return "procrastination"
        case "self_doubt": return "self_loathing"
        default: return nil
        }
    }
}
