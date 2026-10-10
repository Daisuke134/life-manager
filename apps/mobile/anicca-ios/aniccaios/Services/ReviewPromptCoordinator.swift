import Foundation
import StoreKit
import UIKit

/// Persists open-day / last-request state and presents StoreKit review when policy allows.
@MainActor
final class ReviewPromptCoordinator {
    static let shared = ReviewPromptCoordinator()

    private let defaults: UserDefaults
    private let openDaysKey: String
    private let lastRequestKey: String

    init(
        defaults: UserDefaults = .standard,
        openDaysKey: String = "com.anicca.review.openDays",
        lastRequestKey: String = "com.anicca.review.lastRequestAt"
    ) {
        self.defaults = defaults
        self.openDaysKey = openDaysKey
        self.lastRequestKey = lastRequestKey
    }

    /// Call on app activation so distinct open days accumulate.
    func recordAppOpen(now: Date = Date(), calendar: Calendar = .current) {
        let existing = Set(defaults.stringArray(forKey: openDaysKey) ?? [])
        let updated = ReviewPromptPolicy.recordingOpenDay(
            existingDayKeys: existing,
            now: now,
            calendar: calendar
        )
        defaults.set(Array(updated).sorted(), forKey: openDaysKey)
    }

    var distinctOpenDayCount: Int {
        (defaults.stringArray(forKey: openDaysKey) ?? []).count
    }

    var lastReviewRequestAt: Date? {
        let interval = defaults.double(forKey: lastRequestKey)
        guard interval > 0 else { return nil }
        return Date(timeIntervalSince1970: interval)
    }

    /// After a value moment (favorite or finished affirmation session).
    /// Returns whether StoreKit was asked (Apple may still suppress the UI).
    @discardableResult
    func requestReviewIfAppropriate(
        now: Date = Date(),
        calendar: Calendar = .current,
        request: (() -> Void)? = nil
    ) -> Bool {
        let launchArguments = ProcessInfo.processInfo.arguments
        if launchArguments.contains("UITESTING") || launchArguments.contains("-UITESTING") {
            return false
        }

        guard ReviewPromptPolicy.shouldRequestReview(
            distinctOpenDayCount: distinctOpenDayCount,
            lastReviewRequestAt: lastReviewRequestAt,
            now: now,
            calendar: calendar
        ) else {
            return false
        }

        // Record before presenting so a suppressed Apple dialog still counts toward cooldown.
        defaults.set(now.timeIntervalSince1970, forKey: lastRequestKey)
        AppState.shared.markReviewRequested()
        AnalyticsManager.shared.track(.ratingStoreReviewRequested)

        if let request {
            request()
        } else {
            presentSystemReview()
        }
        return true
    }

    private func presentSystemReview() {
        guard let scene = UIApplication.shared.connectedScenes
            .first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene else {
            return
        }
        SKStoreReviewController.requestReview(in: scene)
    }
}
