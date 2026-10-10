import Foundation

/// Decides when an in-app App Store review prompt is allowed.
///
/// Rules (Apple still enforces its own yearly cap on top of these):
/// - Never on first launch
/// - Require opens on at least `minimumDistinctOpenDays` distinct calendar days
/// - At most once every `cooldownDays` days (tracked locally after we ask StoreKit)
/// - Caller must only invoke after a value moment (favorite / session finished)
struct ReviewPromptPolicy: Sendable {
    static let minimumDistinctOpenDays = 3
    static let cooldownDays = 120

    /// Pure gate used at a value moment. Does not mutate storage.
    static func shouldRequestReview(
        distinctOpenDayCount: Int,
        lastReviewRequestAt: Date?,
        now: Date = Date(),
        calendar: Calendar = .current
    ) -> Bool {
        // First launch has 0–1 distinct days; require sustained return visits.
        guard distinctOpenDayCount >= minimumDistinctOpenDays else { return false }

        if let last = lastReviewRequestAt {
            guard let eligibleAt = calendar.date(byAdding: .day, value: cooldownDays, to: last) else {
                return false
            }
            guard now >= eligibleAt else { return false }
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
        let components = calendar.dateComponents([.year, .month, .day], from: date)
        return String(
            format: "%04d-%02d-%02d",
            components.year ?? 0,
            components.month ?? 0,
            components.day ?? 0
        )
    }
}
