import SwiftUI

/// Progress bar for onboarding. Formula: 0.2 + 0.6 * (rawValue / 10).
/// Screen 1 (welcome) = 20%, Screen 11 (notifications) = 80%. Paywall hides the bar.
struct OnboardingProgressBar: View {
    let step: OnboardingStep

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Rectangle()
                    .fill(AppTheme.Colors.label.opacity(0.1))
                    .frame(height: 4)

                Rectangle()
                    .fill(AppTheme.Colors.accent)
                    .frame(
                        width: geometry.size.width * Self.progress(for: step),
                        height: 4
                    )
                    .animation(.easeInOut(duration: 0.4), value: step)
            }
        }
        .frame(height: 4)
    }

    static func progress(for step: OnboardingStep) -> Double {
        let totalSteps = 10.0
        let currentIndex = Double(step.rawValue)
        return 0.2 + 0.6 * (currentIndex / (totalSteps - 1))
    }
}
