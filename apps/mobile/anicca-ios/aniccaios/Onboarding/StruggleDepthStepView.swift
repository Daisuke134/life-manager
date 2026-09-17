import SwiftUI

/// Phase 1: HOOK — frequency question with 1-tap auto-advance.
struct StruggleDepthStepView: View {
    let next: () -> Void
    @EnvironmentObject private var appState: AppState

    private let options: [(key: String, labelKey: String)] = [
        ("daily", "onboarding_depth_daily"),
        ("several_times_week", "onboarding_depth_several"),
        ("weekly", "onboarding_depth_weekly"),
        ("occasionally", "onboarding_depth_occasionally")
    ]

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Text(String(localized: "onboarding_depth_title"))
                .font(.system(size: 32, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.horizontal, 24)

            VStack(spacing: 12) {
                ForEach(options, id: \.key) { option in
                    Button {
                        selectFrequency(option.key)
                    } label: {
                        Text(String(localized: String.LocalizationValue(option.labelKey)))
                            .font(.system(size: 18, weight: .medium))
                            .foregroundStyle(AppTheme.Colors.label)
                            .frame(maxWidth: .infinity)
                            .frame(height: 56)
                            .background(AppTheme.Colors.buttonUnselected)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("onboarding-depth-\(option.key)")
                }
            }
            .padding(.horizontal, 24)

            Spacer()
            Spacer()
        }
        .background(AppBackground())
    }

    private func selectFrequency(_ frequency: String) {
        var profile = appState.userProfile
        profile.struggleFrequency = frequency
        appState.updateUserProfile(profile, sync: true)
        AnalyticsManager.shared.track(.onboardingStruggleDepthCompleted, properties: [
            "frequency": frequency
        ])
        next()
    }
}
