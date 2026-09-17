import SwiftUI

struct StrugglesStepView: View {
    let next: () -> Void
    @EnvironmentObject private var appState: AppState

    /// オンボ抽象カテゴリ → ProblemType 1:1 マッピング
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

    // Bible Screen 3 (5-7 pain points) + Hick's Law: 5 options
    private let options: [String] = [
        "negative_thoughts",
        "putting_off",
        "anxiety_overwhelm",
        "stuck_habit",
        "emotions_take_over"
    ]

    @State private var selected: Set<String> = []

    var body: some View {
        VStack(spacing: 24) {
            Text(String(localized: "onboarding_struggles_title"))
                .font(.system(size: 36, weight: .bold))
                .fontWeight(.heavy)
                .lineSpacing(4) // line-height 40px
                .minimumScaleFactor(0.8)
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.top, 40)
                .padding(.horizontal, 24)

            Text(String(localized: "onboarding_struggles_subtitle"))
                .font(.system(size: 16))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            ScrollView {
                VStack(spacing: 12) {
                    ForEach(options, id: \.self) { key in
                        listRow(kind: "problem", key: key)
                    }
                }
                .padding(.horizontal, 24)
                .padding(.top, 8)
                .padding(.bottom, 16)
            }

            Button {
                var profile = appState.userProfile
                profile.problems = Self.mappedProblems(from: Array(selected))
                appState.updateUserProfile(profile, sync: true)
                next()
            } label: {
                Text(String(localized: "common_next"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: 56)
                    .background(selected.isEmpty ? AppTheme.Colors.label.opacity(0.5) : AppTheme.Colors.label)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .disabled(selected.isEmpty)
            .accessibilityIdentifier("onboarding-struggles-next")
            .padding(.horizontal, 24)
            .padding(.bottom, 64)
        }
        .background(AppBackground())
        .onAppear {
            // Forward-only flow: no restoration needed
        }
    }

    @ViewBuilder
    private func listRow(kind: String, key: String) -> some View {
        let isSelected = selected.contains(key)
        Button {
            if isSelected {
                selected.remove(key)
            } else {
                selected.insert(key)
            }
        } label: {
            HStack(spacing: 12) {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22))
                    .foregroundColor(isSelected ? AppTheme.Colors.accent : .secondary)
                Text(NSLocalizedString("\(kind)_\(key)", comment: ""))
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(AppTheme.Colors.label)
                Spacer()
            }
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity, minHeight: 56)
            .background(isSelected ? AppTheme.Colors.accent.opacity(0.15) : AppTheme.Colors.buttonUnselected)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("onboarding-struggle-\(key)")
    }
}



