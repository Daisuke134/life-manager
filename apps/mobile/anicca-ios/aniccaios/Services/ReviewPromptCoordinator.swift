import Foundation
import StoreKit
import UIKit

/// Persists review-prompt counters in UserDefaults and asks StoreKit when the policy allows.
@MainActor
final class ReviewPromptCoordinator {
    static let shared = ReviewPromptCoordinator()

    static let writeReviewURL = URL(string: "https://apps.apple.com/app/id6755129214?action=write-review")!

    private let defaults: UserDefaults
    private let openDaysKey = "com.anicca.review.openDays"
    private let lastRequestKey = "com.anicca.review.lastRequestAt"
    private let lastVersionKey = "com.anicca.review.lastRequestVersion"
    private let launchCountKey = "com.anicca.review.launchCount"
    private let saveCountKey = "com.anicca.review.saveCount"

    /// Last screen that matters for the gate. Reset to `.other` after each save.
    private(set) var previousScreen: ReviewPromptPreviousScreen = .other

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    static var currentVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"
    }

    /// Call on app activation: counts opens and distinct open days.
    func recordAppOpen(now: Date = Date(), calendar: Calendar = .current) {
        defaults.set(defaults.integer(forKey: launchCountKey) + 1, forKey: launchCountKey)
        let existing = Set(defaults.stringArray(forKey: openDaysKey) ?? [])
        let updated = ReviewPromptPolicy.recordingOpenDay(existingDayKeys: existing, now: now, calendar: calendar)
        defaults.set(Array(updated).sorted(), forKey: openDaysKey)
    }

    /// Paywall, notification permission and error screens call this when shown.
    func noteScreen(_ screen: ReviewPromptPreviousScreen) {
        previousScreen = screen
    }

    var state: ReviewPromptState {
        let interval = defaults.double(forKey: lastRequestKey)
        return ReviewPromptState(
            isOnboardingComplete: AppState.shared.isOnboardingComplete,
            launchCount: defaults.integer(forKey: launchCountKey),
            distinctOpenDayCount: (defaults.stringArray(forKey: openDaysKey) ?? []).count,
            saveCount: defaults.integer(forKey: saveCountKey),
            lastPromptAt: interval > 0 ? Date(timeIntervalSince1970: interval) : nil,
            lastPromptVersion: defaults.string(forKey: lastVersionKey),
            previousScreen: previousScreen
        )
    }

    /// Call right after a card is newly saved (favorited). Counts the save, then
    /// asks StoreKit 0.8s later if every rule passes.
    func cardSaved(request: @escaping () -> Void) {
        defaults.set(defaults.integer(forKey: saveCountKey) + 1, forKey: saveCountKey)
        let snapshot = state
        previousScreen = .other
        DispatchQueue.main.asyncAfter(deadline: .now() + ReviewPromptPolicy.delayAfterSave) { [weak self] in
            self?.requestReviewIfAppropriate(state: snapshot, request: request)
        }
    }

    /// Returns whether StoreKit was asked (Apple may still suppress the UI).
    @discardableResult
    func requestReviewIfAppropriate(
        state: ReviewPromptState,
        now: Date = Date(),
        calendar: Calendar = .current,
        request: () -> Void
    ) -> Bool {
        let args = ProcessInfo.processInfo.arguments
        if args.contains("UITESTING") || args.contains("-UITESTING") { return false }

        let version = Self.currentVersion
        guard ReviewPromptPolicy.shouldRequestReview(state: state, currentVersion: version, now: now, calendar: calendar) else {
            return false
        }

        // Record before presenting so a suppressed Apple dialog still counts.
        defaults.set(now.timeIntervalSince1970, forKey: lastRequestKey)
        defaults.set(version, forKey: lastVersionKey)
        AppState.shared.markReviewRequested()
        AnalyticsManager.shared.track(.ratingStoreReviewRequested)
        AnalyticsManager.shared.trackPostHog("review_prompt_requested", properties: [
            "app_version": version,
            "saves_count": state.saveCount,
            "launch_count": state.launchCount,
            "open_days": state.distinctOpenDayCount
        ])
        request()
        return true
    }
}
