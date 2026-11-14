import SwiftUI

struct StrugglesStepView: View {
    let next: () -> Void
    @EnvironmentObject private var appState: AppState
    @State private var selected: Set<String> = []

    /// Legacy identifiers remain readable by the problem-nudge profile bridge.
    static let problemMapping: [String: String] = [
        "negative_thoughts": "self_loathing",
        "putting_off": "procrastination",
        "anxiety_overwhelm": "anxiety",
        "stuck_habit": "rumination",
        "emotions_take_over": "anger"
    ]

    static func mappedProblems(from struggles: [String]) -> [String] {
        struggles.compactMap { problemMapping[$0] }
    }

    private let options: [(id: String, labelKey: String)] = [
        ("stress", "problem_stress"),
        ("anxiety", "problem_anxiety"),
        ("self_doubt", "problem_self_doubt"),
        ("procrastination", "problem_procrastination"),
        ("sleep", "problem_poor_sleep")
    ]

    var body: some View {
        OnboardingPage(alignment: .leading) {
            Text("Anicca").font(.system(.title, design: .serif))
            Spacer(minLength: 12)
            Text(String(localized: "onboarding_struggles_title"))
                .font(AppTheme.Typography.onboardingTitle)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text(String(localized: "onboarding_struggles_subtitle"))
                .font(.subheadline)
                .foregroundStyle(AppTheme.Colors.secondaryLabel)
                .fixedSize(horizontal: false, vertical: true)
            VStack(spacing: 12) {
                ForEach(options, id: \.id) { option in
                    listRow(option: option)
                }
            }
            Spacer(minLength: 12)
        } footer: {
            PrimaryButton(title: String(localized: "common_next"), isEnabled: !selected.isEmpty, action: saveAndContinue)
                .accessibilityIdentifier("onboarding-struggles-next")
        }
        .onAppear { selected = Set(appState.personalizationProfile.painPointIds) }
    }

    private func saveAndContinue() {
        let chosen = options.map(\.id).filter { selected.contains($0) }
        var personalization = appState.personalizationProfile
        personalization.painPointIds = chosen
        appState.updatePersonalizationProfile(personalization)
        var profile = appState.userProfile
        profile.problems = chosen.compactMap(PersonalizationRules.problemTypeBridge)
        appState.updateUserProfile(profile, sync: true)
        next()
    }

    private func listRow(option: (id: String, labelKey: String)) -> some View {
        let isSelected = selected.contains(option.id)
        return Button {
            if isSelected {
                selected.remove(option.id)
            } else {
                selected.insert(option.id)
            }
        } label: {
            HStack(spacing: 14) {
                Text(NSLocalizedString(option.labelKey, comment: ""))
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isSelected ? AppTheme.Colors.accent : AppTheme.Colors.secondaryLabel)
            }
            .padding(18)
            .selectionCard(isSelected: isSelected)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("onboarding-struggle-\(option.id)")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}
