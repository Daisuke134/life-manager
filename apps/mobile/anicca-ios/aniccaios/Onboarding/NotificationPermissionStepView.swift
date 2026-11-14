import SwiftUI
import UIKit

struct NotificationPermissionStepView: View {
    let next: () -> Void

    @EnvironmentObject private var appState: AppState
    @State private var isRequesting = false
    @State private var hasTrackedPriming = false

    /// Priming: システムダイアログの前に「実際に届く通知そのもの」を見せる。
    /// Phase 1 では planReveal で selector が選び、判断点として記録した
    /// その人の言葉をそのまま通知プレビューとして表示する。
    /// Phase 1 の回答が無い場合は従来の目標→quote 対応表へフォールバック。
    @State private var previewQuoteOverride: Quote?

    private var previewQuote: Quote {
        if let previewQuoteOverride { return previewQuoteOverride }
        let quoteIDs = ["self_love": "q013", "calm": "q021", "confidence": "q041", "focus": "q001"]
        let goal = appState.syntheticUser.answerSnapshot.values["desired_state"]?.first ?? "unknown"
        let id = quoteIDs[goal] ?? "q013"
        return QuoteProvider.shared.byId(id, preferredLanguage: appState.effectiveLanguage)
            ?? QuoteProvider.shared.all(preferredLanguage: appState.effectiveLanguage)[0]
    }

    /// The schedule line shows the slots the user actually chose in the
    /// previous step; the fixed free schedule is only a fallback.
    private var scheduleText: String {
        let user = appState.syntheticUser
        let chosen = PersonalizationRules.effectiveSlots(user: user).map { $0.label }
        if chosen.isEmpty, user.hasAdaptiveAnswers {
            return String(localized: "adaptive_no_available_times")
        }
        if !chosen.isEmpty {
            return String(format: NSLocalizedString("growth_chosen_schedule", comment: ""), chosen.joined(separator: " · "))
        }
        return String(format: NSLocalizedString("growth_reminder_free_schedule", comment: ""), ReminderSchedule.slots(isPro: false).joined(separator: " · "))
    }

    var body: some View {
        OnboardingPage(alignment: .leading) {
            Text("Anicca").font(.system(.title, design: .serif))
            Spacer(minLength: 12)
            Text(String(localized: "onboarding_notifications_title"))
                .font(AppTheme.Typography.onboardingTitle)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text(String(localized: "onboarding_notifications_description"))
                .font(.subheadline)
                .foregroundStyle(AppTheme.Colors.secondaryLabel)
                .fixedSize(horizontal: false, vertical: true)
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 10) {
                    Image("AniccaLogo")
                        .resizable()
                        .scaledToFill()
                        .frame(width: 30, height: 30)
                        .clipShape(RoundedRectangle(cornerRadius: 7))
                    Text("Anicca").font(.system(.headline, design: .serif))
                    Spacer()
                    Text(String(localized: "onboarding_notifications_preview_now"))
                        .font(.caption).foregroundStyle(AppTheme.Colors.secondaryLabel)
                }
                Text(previewQuote.text)
                    .font(.system(.body, design: .serif))
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.cardBackground.opacity(0.85))
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .accessibilityIdentifier("onboarding-notifications-preview")
            Text(scheduleText)
                .font(.subheadline)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 12)
        } footer: {
            VStack(spacing: 12) {
                PrimaryButton(
                    title: String(localized: "onboarding_notifications_allow"),
                    isLoading: isRequesting,
                    action: requestNotifications
                )
                .accessibilityIdentifier("onboarding-notifications-allow")
                Text(String(localized: "onboarding_notifications_optional_hint"))
                    .font(.caption)
                    .foregroundStyle(AppTheme.Colors.secondaryLabel)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Button {
                    AnalyticsManager.shared.track(.notificationPermissionResult, properties: ["result": "skipped"])
                    savePermission("skipped")
                    next()
                } label: {
                    Text(String(localized: "growth_maybe_later"))
                        .font(.subheadline).foregroundStyle(AppTheme.Colors.accent)
                        .frame(minHeight: 44)
                }
                .disabled(isRequesting)
                .accessibilityIdentifier("onboarding-notifications-skip")
            }
        }
        .onAppear {
            if previewQuoteOverride == nil,
               let lastDecision = DecisionPointStore.shared.allCases().last(where: { $0.personId == DecisionPointRecorder.shared.personId && $0.source == "onboarding_preview" }) {
                let messageId = lastDecision.stimulus.messageId
                previewQuoteOverride = QuoteProvider.shared.byId(messageId, preferredLanguage: appState.effectiveLanguage)
            }
            if !hasTrackedPriming {
                hasTrackedPriming = true
                AnalyticsManager.shared.track(.notificationPrimingViewed, properties: [
                    "goal": appState.syntheticUser.answerSnapshot.values["desired_state"]?.first ?? "unknown",
                    "quote_id": previewQuote.id,
                    "flow_id": "onboarding"
                ])
            }
        }
    }

    private func savePermission(_ result: String) {
        var profile = appState.personalizationProfile
        profile.recordNotificationPermission(result)
        appState.updatePersonalizationProfile(profile)
    }

    private func requestNotifications() {
        guard !isRequesting else { return }
        isRequesting = true
        AnalyticsManager.shared.track(.notificationPermissionRequested, properties: ["source": "onboarding"])
        Task {
            let granted = await NotificationScheduler.shared.requestAuthorization()
            await MainActor.run {
                isRequesting = false
                AnalyticsManager.shared.track(.notificationPermissionResult, properties: [
                    "source": "onboarding",
                    "result": granted ? "allowed" : "denied",
                ])
                savePermission(granted ? "allowed" : "denied")
                if granted {
                    // v1.8.7: notifications are remote-only (APNs). Register now that
                    // the user granted permission so the device token reaches the backend.
                    UIApplication.shared.registerForRemoteNotifications()
                }
                next()
            }
        }
    }
}
