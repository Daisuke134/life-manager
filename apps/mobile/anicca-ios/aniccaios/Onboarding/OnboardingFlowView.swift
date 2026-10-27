import SwiftUI
import RevenueCat
import RevenueCatUI
import UserNotifications

/// v8 onboarding: 10 steps + 2-step SOFT paywall (no in-flow rating prompt).
/// Paywall presented via .fullScreenCover + .interactiveDismissDisabled (スワイプ離脱は防止)。
/// 右上の × (paywall-close-button) タップでのみ課金せずメイン画面へ遷移する。
struct OnboardingFlowView: View {
    @EnvironmentObject private var appState: AppState
    @State private var step: OnboardingStep = .welcome
    @State private var showPaywall: Bool = false
    @State private var isResolvingPaywallEntry = false
    @State private var didPurchaseOnPaywall = false

    var body: some View {
        ZStack {
            AppBackground()

            VStack(spacing: 0) {
                OnboardingProgressBar(step: step)
                    .padding(.horizontal, 16)
                    .padding(.top, 8)

                Group {
                    onboardingContent(for: step)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }

            if isResolvingPaywallEntry {
                ProgressView()
                    .accessibilityIdentifier("onboarding-paywall-entitlement-check")
            }
        }
        .onAppear {
            if appState.onboardingQuestionsCompleted {
                resolveOnboardingPaywallEntry(source: "resume")
                return
            }

            step = appState.onboardingStep

            if step == .welcome {
                AnalyticsManager.shared.track(.onboardingStarted)
            }

            Task {
                await SubscriptionManager.shared.refreshOfferings()
            }
        }
        .fullScreenCover(isPresented: $showPaywall) {
            PaywallFlowContainer(
                onPurchaseSuccess: { customerInfo in
                    handlePaywallSuccess(customerInfo: customerInfo)
                },
                onDismiss: {
                    handlePaywallDismissedAsFree()
                }
            )
            .interactiveDismissDisabled(true)
        }
    }

    // MARK: - Onboarding Steps

    @ViewBuilder
    private func onboardingContent(for step: OnboardingStep) -> some View {
        switch step {
        case .welcome:          WelcomeStepView(next: advance)
        case .goal:             GoalStepView(next: advance)
        case .painPoints:       StrugglesStepView(next: advance)
        case .struggleFreq:     StruggleDepthStepView(next: advance)
        case .nudgeTimes:       PreferredNudgeTimesView(next: advance)
        case .processing:       ProcessingStepView(next: advance)
        case .planReveal:       PersonalizedInsightStepView(next: advance)
        case .comparison:       ComparisonTableStepView(next: advance)
        case .notifications:    NotificationPermissionStepView(next: advance)
        }
    }

    // MARK: - Navigation

    private func advance() {
        AnalyticsManager.shared.track(.onboardingStepAdvanced, properties: ["step": step.analyticsName])

        if step == .notifications {
            appState.markOnboardingQuestionsCompleted()
            AnalyticsManager.shared.track(.onboardingCompleted)
            AnalyticsManager.shared.updateSKANConversionValue(1)
            resolveOnboardingPaywallEntry(source: "completion")
            return
        }

        if let next = OnboardingStep(rawValue: step.rawValue + 1) {
            step = next
            appState.setOnboardingStep(step)
        }
    }

    private func completeOnboardingForExistingPro() {
        // v1.8.7: remote-only notifications. APNs registration is triggered on
        // permission grant and on app foreground — nothing to schedule locally.
        appState.markOnboardingComplete()
    }

    @MainActor
    private func resolveOnboardingPaywallEntry(source: String) {
        guard !isResolvingPaywallEntry else { return }
        isResolvingPaywallEntry = true
        Task { @MainActor in
            let freshEntitlement = await SubscriptionManager.shared.refreshCustomerInfo()
            let cachedEntitlement = appState.subscriptionInfo.isEntitled
            let result: String
            if let freshEntitlement {
                result = freshEntitlement ? "fresh_entitled" : "fresh_not_entitled"
            } else {
                result = cachedEntitlement ? "unavailable_cached_entitled" : "unavailable_cached_free"
            }
            AnalyticsManager.shared.track(.onboardingPaywallCustomerInfoResult, properties: [
                "source": source,
                "result": result,
            ])

            let decision = OnboardingPaywallDecision.resolve(
                freshEntitlement: freshEntitlement,
                cachedEntitlement: cachedEntitlement
            )
            isResolvingPaywallEntry = false
            switch decision {
            case .completeOnboarding:
                completeOnboardingForExistingPro()
            case .presentPaywall:
                showPaywall = true
            }
        }
    }

    private func handlePaywallSuccess(customerInfo: CustomerInfo) {
        didPurchaseOnPaywall = true
        appState.updateSubscriptionInfo(from: customerInfo)
        appState.markOnboardingComplete()
        showPaywall = false
    }

    /// ソフトペイウォール: 右上 × で課金せずメイン画面へ。
    private func handlePaywallDismissedAsFree() {
        AnalyticsManager.shared.track(.onboardingPaywallDismissedFree)
        appState.markOnboardingComplete()
        showPaywall = false
    }
}
