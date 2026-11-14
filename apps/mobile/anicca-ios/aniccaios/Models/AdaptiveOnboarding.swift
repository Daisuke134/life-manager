import Foundation

/// Stable answer vocabulary. Labels live in Localizable.strings, never in storage.
enum OnboardingQuestion: String, CaseIterable {
    case birthContext = "birth_context"
    case moodBaseline = "mood_baseline"
    case beliefThemes = "belief_themes"
    case tone
    case lifeContext = "life_context"
    case routineAnchors = "routine_anchors"
    case priorAttempts = "prior_attempts"
    case startReason = "start_reason"
    case quietHours = "quiet_hours"
    case stressTrigger = "stress_trigger"
    case anxietyTarget = "anxiety_target"
    case selfCriticism = "self_criticism"
    case avoidanceTask = "avoidance_task"
    case sleepReason = "sleep_reason"
    case bedtime
    case wakeTime = "wake_time"
    case priorHelpfulness = "prior_helpfulness"

    var optionIDs: [String] {
        switch self {
        case .birthContext: return ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"]
        case .moodBaseline: return ["very_heavy", "heavy", "neutral", "light", "very_light"]
        case .beliefThemes: return ["self_trust", "inner_peace", "courage", "forgiveness", "gratitude"]
        case .tone: return ["gentle", "direct", "poetic", "practical"]
        case .lifeContext: return ["work", "caregiving", "study", "transition", "none"]
        case .routineAnchors: return ["waking", "commute", "lunch", "bedtime", "none"]
        case .priorAttempts: return ["meditation", "journaling", "therapy", "books", "first_time"]
        case .startReason: return ["overwhelmed", "new_chapter", "recommended", "curious"]
        case .quietHours: return ["morning", "afternoon", "evening", "overnight", "none"]
        case .stressTrigger: return ["work", "social", "morning", "night"]
        case .anxietyTarget: return ["future", "judgment", "health", "money"]
        case .selfCriticism: return ["work", "relationships", "appearance", "parenting"]
        case .avoidanceTask: return ["work", "messages", "chores", "personal_plan"]
        case .sleepReason: return ["racing_mind", "body_clock", "screens"]
        case .bedtime: return ["before_22", "22_to_24", "after_midnight"]
        case .wakeTime: return ["before_6", "6_to_8", "after_8"]
        case .priorHelpfulness: return ["meditation", "journaling", "therapy", "books", "none"]
        }
    }

    var allowsMultiple: Bool {
        [OnboardingQuestion.beliefThemes, .lifeContext, .routineAnchors, .priorAttempts, .quietHours, .priorHelpfulness].contains(self)
    }

    var exclusiveOption: String? {
        switch self {
        case .lifeContext, .routineAnchors, .quietHours, .priorHelpfulness: return "none"
        case .priorAttempts: return "first_time"
        default: return nil
        }
    }

    var step: OnboardingStep {
        switch self {
        case .birthContext: return .birthContext
        case .moodBaseline: return .moodBaseline
        case .beliefThemes: return .beliefThemes
        case .tone: return .tone
        case .lifeContext: return .lifeContext
        case .routineAnchors: return .routineAnchors
        case .priorAttempts: return .priorAttempts
        case .startReason: return .startReason
        case .quietHours: return .quietHours
        case .stressTrigger: return .stressTrigger
        case .anxietyTarget: return .anxietyTarget
        case .selfCriticism: return .selfCriticism
        case .avoidanceTask: return .avoidanceTask
        case .sleepReason: return .sleepReason
        case .bedtime: return .bedtime
        case .wakeTime: return .wakeTime
        case .priorHelpfulness: return .priorHelpfulness
        }
    }

    func options(answers: AdaptiveAnswers) -> [String] {
        guard self == .priorHelpfulness else { return optionIDs }
        let tried = answers.ids(for: .priorAttempts)
        return optionIDs.filter { $0 == "none" || tried.contains($0) }
    }
}

struct AdaptiveAnswers: Codable, Equatable {
    var values: [String: [String]] = [:]
    /// Device-only. Neither snapshots nor the sync payload encode this value.
    var birthDate: Date?

    func ids(for question: OnboardingQuestion) -> [String] {
        let values = self.values[question.rawValue] ?? []
        let valid = question.optionIDs.filter { values.contains($0) }
        if let exclusive = question.exclusiveOption, valid.contains(exclusive) { return [exclusive] }
        return question.allowsMultiple ? valid : Array(valid.prefix(1))
    }

    mutating func set(_ question: OnboardingQuestion, ids: [String]) {
        values[question.rawValue] = ids
        values[question.rawValue] = self.ids(for: question)
        if values[question.rawValue]?.isEmpty == true { values[question.rawValue] = ["unknown"] }
    }

    mutating func setBirthContext(birthDate: Date?, zodiacIDs: [String]) {
        self.birthDate = birthDate
        // date_provided belongs to the exported snapshot, not the selectable signs.
        set(.birthContext, ids: birthDate == nil ? zodiacIDs : [])
    }

    func ageBand(now: Date, calendar: Calendar = .current) -> String {
        guard let birthDate, birthDate <= now,
              let age = calendar.dateComponents([.year], from: birthDate, to: now).year,
              (0...125).contains(age) else { return "unknown" }
        switch age {
        case 0..<18: return "under_18"
        case 18..<25: return "18_24"
        case 25..<35: return "25_34"
        case 35..<45: return "35_44"
        case 45..<55: return "45_54"
        case 55..<65: return "55_64"
        default: return "65_plus"
        }
    }

    /// Calendar context only, never personality or predicted behavior from a sign.
    func isBirthdaySeason(now: Date, calendar: Calendar = Calendar(identifier: .gregorian)) -> Bool {
        if let birthDate {
            return calendar.component(.month, from: birthDate) == calendar.component(.month, from: now)
        }
        let season = ["capricorn", "aquarius", "pisces", "aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius"]
        let month = calendar.component(.month, from: now) - 1
        let day = calendar.component(.day, from: now)
        let boundaries = [20, 19, 21, 20, 21, 21, 23, 23, 23, 23, 22, 22]
        let currentSign = season[(month + (day >= boundaries[month] ? 1 : 0)) % 12]
        return ids(for: .birthContext).first == currentSign
    }
}

/// The export boundary contains enumerated IDs and a version, never raw profile data.
struct OnboardingAnswerSnapshot: Codable, Equatable {
    let version: Int
    let values: [String: [String]]

    var analyticsIDs: [String] {
        values.keys.sorted().flatMap { axis in
            (values[axis] ?? []).map { "\(axis):\($0)" }
        }
    }
}

extension PersonalizationProfile {
    var answers: AdaptiveAnswers { adaptiveAnswers ?? AdaptiveAnswers() }

    mutating func recordNotificationPermission(_ result: String) {
        // A legacy resume at permission must not create adaptive answers.
        adaptiveAnswers?.values["notification_permission"] = [result]
    }

    func answerSnapshot(now: Date = Date()) -> OnboardingAnswerSnapshot {
        var result: [String: [String]] = [:]
        let activeSteps = OnboardingStep.journey(painPointIds: painPointIds, priorAttempts: answers.ids(for: .priorAttempts))
        for question in OnboardingQuestion.allCases {
            if !activeSteps.contains(question.step) {
                result[question.rawValue] = ["not_asked"]
            } else if question == .birthContext, answers.birthDate != nil {
                result[question.rawValue] = ["date_provided"]
            } else {
                var ids = answers.ids(for: question)
                if question == .priorHelpfulness {
                    ids = ids.filter { answers.optionsForPriorHelpfulness.contains($0) }
                }
                result[question.rawValue] = ids.isEmpty ? ["unknown"] : ids
            }
        }
        result["age_band"] = [answers.ageBand(now: now)]
        result["desired_state"] = [Self.enumerated(desiredState, allowed: ["calm", "confidence", "focus", "self_love"])]
        let pain = ["stress", "anxiety", "self_doubt", "procrastination", "sleep"].filter { painPointIds.contains($0) }
        result["pain_points"] = pain.isEmpty ? ["unknown"] : pain
        result["struggle_frequency"] = [Self.enumerated(struggleFrequency, allowed: ["rarely", "weekly", "daily", "many_times_daily"])]
        result["name_status"] = [preferredName == nil ? "unknown" : "provided"]
        result["notification_permission"] = [Self.enumerated(answers.values["notification_permission"]?.first,
            allowed: ["allowed", "denied", "skipped"])]
        result["reminder_slots"] = nudgeSlots.compactMap { slot in
            PersonalizationRules.presetSlots.contains(slot) ? "slot_\(slot.hour)_\(slot.minute)" : nil
        }
        result["daily_frequency"] = [(1...3).contains(dailyFrequency) ? ["one", "two", "three"][dailyFrequency - 1] : "unknown"]
        return OnboardingAnswerSnapshot(version: 2, values: result)
    }

    private static func enumerated(_ value: String?, allowed: [String]) -> String {
        guard let value, allowed.contains(value) else { return "unknown" }
        return value
    }
}

private extension AdaptiveAnswers {
    var optionsForPriorHelpfulness: [String] { OnboardingQuestion.priorHelpfulness.options(answers: self) }
}

extension PersonalizationRules {
    static func intensity(struggleFrequency: String?, moodBaseline: String?) -> String {
        if ["heavy", "very_heavy"].contains(moodBaseline ?? "") { return "gentle" }
        return intensity(struggleFrequency: struggleFrequency)
    }

    static func intensity(profile: PersonalizationProfile) -> String {
        intensity(struggleFrequency: profile.struggleFrequency, moodBaseline: profile.answers.ids(for: .moodBaseline).first)
    }

    static func isQuiet(_ slot: NudgeSlot, quietHours: [String]) -> Bool {
        let minute = slot.hour * 60 + slot.minute
        return quietHours.contains { band in
            switch band {
            case "morning": return (360..<720).contains(minute)
            case "afternoon": return (720..<1080).contains(minute)
            case "evening": return (1080..<1320).contains(minute)
            case "overnight": return minute >= 1320 || minute < 360
            default: return false
            }
        }
    }

    static func availableSlots(profile: PersonalizationProfile) -> [NudgeSlot] {
        presetSlots.filter { !isQuiet($0, quietHours: profile.answers.ids(for: .quietHours)) }
    }

    /// Preserve explicit choices; a quiet-hours conflict suppresses, never relocates.
    static func effectiveSlots(profile: PersonalizationProfile) -> [NudgeSlot] {
        Array(profile.nudgeSlots.sorted().prefix(max(0, profile.dailyFrequency))).filter {
            !isQuiet($0, quietHours: profile.answers.ids(for: .quietHours))
        }
    }

    static func initialSlots(profile: PersonalizationProfile, frequency: Int) -> [NudgeSlot] {
        if !profile.nudgeSlots.isEmpty { return profile.nudgeSlots.sorted() }
        let anchors = profile.answers.ids(for: .routineAnchors)
        var proposed: [NudgeSlot] = []
        if anchors.contains("waking") || anchors.contains("commute") { proposed.append(presetSlots[0]) }
        if anchors.contains("lunch") { proposed.append(presetSlots[1]) }
        if anchors.contains("bedtime") { proposed.append(presetSlots[3]) }
        if proposed.isEmpty {
            if profile.painPointIds.contains("sleep"), profile.answers.ids(for: .bedtime).contains("before_22") {
                proposed = [presetSlots[2], presetSlots[1], presetSlots[0]]
            } else {
                proposed = proposedSlots(painPointIds: profile.painPointIds, frequency: frequency)
            }
        }
        // Only proposals may fill from the remaining available presets.
        for slot in presetSlots where !proposed.contains(slot) { proposed.append(slot) }
        let allowed = proposed.filter { !isQuiet($0, quietHours: profile.answers.ids(for: .quietHours)) }
        return Array(allowed.prefix(min(max(frequency, 1), freeFrequencyCap))).sorted()
    }
}
