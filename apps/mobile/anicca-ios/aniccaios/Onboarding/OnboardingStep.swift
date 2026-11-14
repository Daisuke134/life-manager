import Foundation

/// Persisted raw values remain stable; the initial journey selects only value-bearing screens.
enum OnboardingStep: Int, CaseIterable, Codable {
    case welcome = 0
    case goal = 1
    case painPoints = 2
    case struggleFreq = 3
    case nudgeTimes = 4
    case processing = 5
    case planReveal = 6
    case comparison = 7
    case notifications = 8
    case name = 9
    case birthContext = 10
    case moodBaseline = 11
    case beliefThemes = 12
    case tone = 13
    case lifeContext = 14
    case routineAnchors = 15
    case priorAttempts = 16
    case startReason = 17
    case quietHours = 18
    case stressTrigger = 19
    case anxietyTarget = 20
    case selfCriticism = 21
    case avoidanceTask = 22
    case sleepReason = 23
    case bedtime = 24
    case wakeTime = 25
    case priorHelpfulness = 26
}

enum PaywallStep: Int, CaseIterable, Codable {
    case primer = 0
    case planSelection = 1
}

extension OnboardingStep {
    /// Introduce the product, then ask one question per screen before the
    /// personalized preview, reminder schedule and optional permission.
    static let initialJourney = journey(painPointIds: [])

    static func deepDiveSteps(painPointIds: [String]) -> [OnboardingStep] {
        let modules: [(String, [OnboardingStep])] = [
            ("stress", [.stressTrigger]), ("anxiety", [.anxietyTarget]),
            ("self_doubt", [.selfCriticism]), ("procrastination", [.avoidanceTask]),
            ("sleep", [.sleepReason, .bedtime, .wakeTime])
        ]
        return modules.filter { painPointIds.contains($0.0) }.prefix(2).flatMap { $0.1 }
    }

    static func journey(painPointIds: [String], priorAttempts: [String] = []) -> [OnboardingStep] {
        let experienceFollowUp: [OnboardingStep] = priorAttempts.contains(where: {
            ["meditation", "journaling", "therapy", "books"].contains($0)
        }) ? [.priorHelpfulness] : []
        return [.welcome, .goal, .name, .birthContext, .moodBaseline, .painPoints]
            + deepDiveSteps(painPointIds: painPointIds)
            + [.struggleFreq, .beliefThemes, .tone, .lifeContext, .routineAnchors, .priorAttempts]
            + experienceFollowUp
            + [.startReason, .quietHours, .planReveal, .nudgeTimes, .notifications]
    }

    func resumableStep(painPointIds: [String], priorAttempts: [String] = []) -> OnboardingStep {
        let step = resumableInitialStep
        if Self.journey(painPointIds: painPointIds, priorAttempts: priorAttempts).contains(step) { return step }
        return step == .priorHelpfulness ? .startReason : .struggleFreq
    }

    func nextStep(painPointIds: [String], priorAttempts: [String] = []) -> OnboardingStep? {
        let journey = Self.journey(painPointIds: painPointIds, priorAttempts: priorAttempts)
        let current = resumableStep(painPointIds: painPointIds, priorAttempts: priorAttempts)
        guard let index = journey.firstIndex(of: current), index + 1 < journey.count else { return nil }
        return journey[index + 1]
    }

    var resumableInitialStep: OnboardingStep {
        switch self {
        case .processing, .comparison: return .planReveal
        default: return self
        }
    }

    var nextInitialStep: OnboardingStep? {
        guard let index = Self.initialJourney.firstIndex(of: resumableInitialStep),
              index + 1 < Self.initialJourney.count else { return nil }
        return Self.initialJourney[index + 1]
    }

    /// v7 (11-step, rating at 8) → v8 (10-step, no rating).
    static func migratedFromV7RawValue(_ rawValue: Int) -> OnboardingStep? {
        switch rawValue {
        case 0...7:
            return OnboardingStep(rawValue: rawValue)
        case 8, 9:
            // ratingPrompt(8) and notifications(9) both land on notifications(8)
            return .notifications
        default:
            return nil
        }
    }

    /// v6 (19-step) → v8 (10-step) migration.
    /// Removed: age(1), tinderPain(5), whatTried(6), stressLevel(7), socialProof(8), meditExp(10), valueTimeline(13), valueDelivery(16), ratingPrompt
    static func migratedFromV6RawValue(_ rawValue: Int) -> OnboardingStep? {
        switch rawValue {
        case 0: return .welcome
        case 1: return .goal              // age → skip to goal
        case 2: return .goal
        case 3: return .painPoints
        case 4: return .struggleFreq
        case 5: return .nudgeTimes        // tinderPain → skip to nudgeTimes
        case 6: return .nudgeTimes        // whatTried → skip to nudgeTimes
        case 7: return .nudgeTimes        // stressLevel → skip to nudgeTimes
        case 8: return .nudgeTimes        // socialProof → skip to nudgeTimes
        case 9: return .nudgeTimes
        case 10: return .processing       // meditExp → skip to processing
        case 11: return .processing
        case 12: return .planReveal
        case 13: return .comparison       // valueTimeline → skip to comparison
        case 14: return .comparison
        case 15, 16, 17, 18:
            // appDemo / valueDelivery / ratingPrompt / notifications → notifications
            return .notifications
        default: return nil
        }
    }
}

extension OnboardingStep {
    var analyticsName: String {
        switch self {
        case .welcome: return "welcome"
        case .goal: return "goal"
        case .name: return "name"
        case .birthContext: return "birth_context"
        case .moodBaseline: return "mood_baseline"
        case .beliefThemes: return "belief_themes"
        case .tone: return "tone"
        case .lifeContext: return "life_context"
        case .routineAnchors: return "routine_anchors"
        case .priorAttempts: return "prior_attempts"
        case .startReason: return "start_reason"
        case .quietHours: return "quiet_hours"
        case .stressTrigger: return "stress_trigger"
        case .anxietyTarget: return "anxiety_target"
        case .selfCriticism: return "self_criticism"
        case .avoidanceTask: return "avoidance_task"
        case .sleepReason: return "sleep_reason"
        case .bedtime: return "bedtime"
        case .wakeTime: return "wake_time"
        case .priorHelpfulness: return "prior_helpfulness"
        case .painPoints: return "pain_points"
        case .struggleFreq: return "struggle_freq"
        case .nudgeTimes: return "nudge_times"
        case .processing: return "processing"
        case .planReveal: return "plan_reveal"
        case .comparison: return "comparison"
        case .notifications: return "notifications"
        }
    }
}
