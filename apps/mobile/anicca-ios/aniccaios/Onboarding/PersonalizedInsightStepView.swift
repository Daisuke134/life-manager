import SwiftUI

/// Phase 2: INVEST — stats + path visualization based on user answers.
struct PersonalizedInsightStepView: View {
    let next: () -> Void

    @State private var showContent = false

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            VStack(spacing: 24) {
                Text(String(localized: "onboarding_insight_title"))
                    .font(.system(size: 28, weight: .bold))
                    .foregroundStyle(AppTheme.Colors.label)
                    .multilineTextAlignment(.center)

                Text(String(localized: "onboarding_insight_stat"))
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(AppTheme.Colors.accent)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
                    .opacity(showContent ? 1 : 0)
                    .offset(y: showContent ? 0 : 20)

                Text(String(localized: "onboarding_insight_message"))
                    .font(.system(size: 16))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .opacity(showContent ? 1 : 0)
                    .offset(y: showContent ? 0 : 20)
            }

            Spacer()

            Button {
                AnalyticsManager.shared.track(.onboardingInsightCompleted)
                next()
            } label: {
                Text(String(localized: "onboarding_insight_cta"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: 56)
                    .background(AppTheme.Colors.label)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .accessibilityIdentifier("onboarding-insight-cta")
            .padding(.horizontal, 24)
            .padding(.bottom, 64)
            .opacity(showContent ? 1 : 0)
        }
        .background(AppBackground())
        .onAppear {
            withAnimation(.easeOut(duration: 0.8).delay(0.3)) {
                showContent = true
            }
        }
    }
}
