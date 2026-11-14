import SwiftUI

/// Progress follows the displayed journey, independent of persisted raw values.
struct OnboardingProgressBar: View {
    let step: OnboardingStep
    var journey: [OnboardingStep] = OnboardingStep.initialJourney

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Rectangle()
                    .fill(AppTheme.Colors.label.opacity(0.1))
                    .frame(height: 4)

                Rectangle()
                    .fill(AppTheme.Colors.accent)
                    .frame(
                        width: geometry.size.width * Self.progress(for: step, journey: journey),
                        height: 4
                    )
                    .animation(.easeInOut(duration: 0.4), value: step)
            }
        }
        .frame(height: 4)
    }

    static func progress(for step: OnboardingStep, journey: [OnboardingStep] = OnboardingStep.initialJourney) -> Double {
        let index = journey.firstIndex(of: step.resumableInitialStep) ?? 0
        return Double(index + 1) / Double(max(journey.count, 1))
    }
}
