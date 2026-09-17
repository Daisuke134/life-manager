import SwiftUI
import RevenueCat
import RevenueCatUI
import UserNotifications
import StoreKit

/// v7 onboarding: 11 steps + 2-step SOFT paywall.
/// Paywall presented via .fullScreenCover + .interactiveDismissDisabled (スワイプ離脱は防止)。
/// 右上の × (paywall-close-button) タップでのみ課金せずメイン画面へ遷移する。
struct OnboardingFlowView: View {
    @EnvironmentObject private var appState: AppState
    @State private var step: OnboardingStep = .welcome
    @State private var showPaywall: Bool = false
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
        }
        .onAppear {
            if appState.onboardingQuestionsCompleted && !appState.subscriptionInfo.isEntitled {
                showPaywall = true
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
        case .ratingPrompt:     RatingPrePromptStepView(next: advance)
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

            if appState.subscriptionInfo.isEntitled {
                completeOnboardingForExistingPro()
                return
            }

            showPaywall = true
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
