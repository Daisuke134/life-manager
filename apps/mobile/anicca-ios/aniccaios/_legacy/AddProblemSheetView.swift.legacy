import SwiftUI

// MARK: - AddProblemSheetView
struct AddProblemSheetView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var selected: Set<String> = []

    private let allProblems: [String] = [
        "staying_up_late", "cant_wake_up", "self_loathing",
        "rumination", "procrastination", "anxiety",
        "lying", "bad_mouthing", "porn_addiction",
        "alcohol_dependency", "anger", "obsessive",
        "loneliness"
    ]

    private var availableProblems: [String] {
        let current = Set(appState.userProfile.problems)
        return allProblems.filter { !current.contains($0) }
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Text(String(localized: "add_problem_title"))
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.label)
                    .padding(.top, 24)

                Text(String(localized: "add_problem_subtitle"))
                    .font(.subheadline)
                    .foregroundStyle(AppTheme.Colors.secondaryLabel)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)

                if availableProblems.isEmpty {
                    emptyStateView
                } else {
                    ScrollView {
                        FlowLayout(spacing: 12) {
                            ForEach(availableProblems, id: \.self) { key in
                                chipButton(key: key)
                            }
                        }
                        .padding(.horizontal, 24)
                    }
                }

                Spacer()

                PrimaryButton(
                    title: String(localized: "add_problem_add_button"),
                    isEnabled: !selected.isEmpty,
                    style: .large
                ) {
                    addSelectedProblems()
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 32)
            }
            .background(AppBackground())
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: { dismiss() }) {
                        Image(systemName: "xmark")
                            .foregroundStyle(AppTheme.Colors.secondaryLabel)
                    }
                }
            }
        }
    }

    private var emptyStateView: some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 48))
                .foregroundStyle(AppTheme.Colors.buttonSelected)
            Text(String(localized: "add_problem_all_selected"))
                .font(.headline)
                .foregroundStyle(AppTheme.Colors.label)
        }
        .padding(40)
    }

    @ViewBuilder
    private func chipButton(key: String) -> some View {
        let isSelected = selected.contains(key)
        Button {
            if isSelected {
                selected.remove(key)
            } else {
                selected.insert(key)
            }
        } label: {
            Text(NSLocalizedString("problem_\(key)", comment: ""))
                .font(.system(size: 16, weight: .medium))
                .fixedSize(horizontal: true, vertical: false)
                .padding(.horizontal, 20)
                .padding(.vertical, 14)
                .background(isSelected ? AppTheme.Colors.buttonSelected : AppTheme.Colors.buttonUnselected)
                .foregroundStyle(isSelected ? AppTheme.Colors.buttonTextSelected : AppTheme.Colors.label)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    private func addSelectedProblems() {
        var profile = appState.userProfile
        profile.problems.append(contentsOf: selected)
        appState.updateUserProfile(profile, sync: true)

        // 通知をスケジュール
        Task {
            await ProblemNotificationScheduler.shared.scheduleNotifications(for: profile.problems)
        }

        dismiss()
    }
}

