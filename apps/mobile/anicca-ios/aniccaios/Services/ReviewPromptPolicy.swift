import Foundation

/// Screen the user saw right before the value moment. The prompt never follows
/// the paywall, the notification permission ask, or an error.
enum ReviewPromptPreviousScreen: String, Sendable {
    case other
    case paywall
    case notificationPermission
    case error

    var blocksReviewPrompt: Bool { self != .other }
}

/// Snapshot of everything the gate needs. Pure value; no storage access.
struct ReviewPromptState: Equatable, Sendable {
    var isOnboardingComplete: Bool
    var launchCount: Int
    var distinctOpenDayCount: Int
    var saveCount: Int
    var lastPromptAt: Date?
    var lastPromptVersion: String?
    var previousScreen: ReviewPromptPreviousScreen
}

/// Decides when an in-app App Store review prompt is allowed.
/// Spec: team/gaps/GAP-appstore-anicca.md "Rating prompt" (2026-11-02).
/// Apple still enforces its own cap (3 per 365 days) on top of these rules.
struct ReviewPromptPolicy: Sendable {
    static let minimumLaunchCount = 3
    static let minimumDistinctOpenDays = 2
    static let minimumSaveCount = 3
    static let cooldownDays = 120
    /// Delay after the save animation before asking StoreKit.
    static let delayAfterSave: TimeInterval = 0.8

    static func shouldRequestReview(
        state: ReviewPromptState,
        currentVersion: String,
        now: Date = Date(),
        calendar: Calendar = .current
    ) -> Bool {
        guard state.isOnboardingComplete else { return false }
        guard state.launchCount >= minimumLaunchCount else { return false }
        guard state.distinctOpenDayCount >= minimumDistinctOpenDays else { return false }
        guard state.saveCount >= minimumSaveCount else { return false }
        guard !state.previousScreen.blocksReviewPrompt else { return false }
        // At most once per app version.
        if let lastVersion = state.lastPromptVersion, lastVersion == currentVersion { return false }
        // At least 120 days since the previous prompt.
        if let last = state.lastPromptAt {
            guard let eligibleAt = calendar.date(byAdding: .day, value: cooldownDays, to: last),
                  now >= eligibleAt else { return false }
        }
        return true
    }

    /// Inserts today's day key into the open-day set (idempotent per calendar day).
    static func recordingOpenDay(
        existingDayKeys: Set<String>,
        now: Date = Date(),
        calendar: Calendar = .current
    ) -> Set<String> {
        var updated = existingDayKeys
        updated.insert(dayKey(for: now, calendar: calendar))
        return updated
    }

    static func dayKey(for date: Date, calendar: Calendar = .current) -> String {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year ?? 0, c.month ?? 0, c.day ?? 0)
    }
}
