import Foundation

/// v7 Onboarding flow — 11 steps + 2 paywall.
enum OnboardingStep: Int, CaseIterable, Codable {
    case welcome = 0
    case goal = 1
    case painPoints = 2
    case struggleFreq = 3
    case nudgeTimes = 4
    case processing = 5
    case planReveal = 6
    case comparison = 7
    case ratingPrompt = 8
    case notifications = 9
}

enum PaywallStep: Int, CaseIterable, Codable {
    case primer = 0
    case planSelection = 1
}

extension OnboardingStep {
    /// v6 (19-step) → v7 (11-step) migration.
    /// Removed: age(1), tinderPain(5), whatTried(6), stressLevel(7), socialProof(8), meditExp(10), valueTimeline(13), valueDelivery(16)
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
        case 15: return .ratingPrompt     // appDemo removed → skip to ratingPrompt
        case 16: return .ratingPrompt     // valueDelivery → skip to ratingPrompt
        case 17: return .ratingPrompt
        case 18: return .notifications
        default: return nil
        }
    }
}

extension OnboardingStep {
    var analyticsName: String {
        switch self {
        case .welcome: return "welcome"
        case .goal: return "goal"
        case .painPoints: return "pain_points"
        case .struggleFreq: return "struggle_freq"
        case .nudgeTimes: return "nudge_times"
        case .processing: return "processing"
        case .planReveal: return "plan_reveal"
        case .comparison: return "comparison"
        case .ratingPrompt: return "rating_prompt"
        case .notifications: return "notifications"
        }
    }
}
