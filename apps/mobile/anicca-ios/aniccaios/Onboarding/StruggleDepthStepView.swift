import SwiftUI

struct StruggleDepthStepView: View {
    let next: () -> Void
    @EnvironmentObject private var appState: AppState
    @State private var selected: String?

    private let options: [(key: String, labelKey: String)] = [
        ("rarely", "onboarding_depth_rarely"),
        ("weekly", "onboarding_depth_weekly"),
        ("daily", "onboarding_depth_daily"),
        ("many_times_daily", "onboarding_depth_many_times_daily")
    ]

    var body: some View {
        OnboardingPage(alignment: .leading) {
            Text("Anicca").font(.system(.title, design: .serif))
            Spacer(minLength: 12)
            Text(String(localized: "onboarding_depth_title"))
                .font(AppTheme.Typography.onboardingTitle)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            VStack(spacing: 12) {
                ForEach(options, id: \.key) { option in
                    Button {
                        selected = option.key
                    } label: {
                        HStack(spacing: 14) {
                            Text(String(localized: String.LocalizationValue(option.labelKey)))
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 8)
                            Image(systemName: selected == option.key ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(selected == option.key ? AppTheme.Colors.accent : AppTheme.Colors.secondaryLabel)
                        }
                        .padding(18)
                        .selectionCard(isSelected: selected == option.key)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("onboarding-depth-\(option.key)")
                    .accessibilityAddTraits(selected == option.key ? .isSelected : [])
                }
            }
            Spacer(minLength: 12)
        } footer: {
            PrimaryButton(title: String(localized: "common_continue"), isEnabled: selected != nil) {
                if let selected { selectFrequency(selected) }
            }
            .accessibilityIdentifier("onboarding-depth-continue")
        }
        .onAppear { selected = appState.personalizationProfile.struggleFrequency }
    }

    private func selectFrequency(_ frequency: String) {
        var profile = appState.userProfile
        profile.struggleFrequency = frequency
        appState.updateUserProfile(profile, sync: true)
        var personalization = appState.personalizationProfile
        personalization.struggleFrequency = frequency
        appState.updatePersonalizationProfile(personalization)
        AnalyticsManager.shared.track(.onboardingStruggleDepthCompleted, properties: ["frequency": frequency])
        next()
    }
}
