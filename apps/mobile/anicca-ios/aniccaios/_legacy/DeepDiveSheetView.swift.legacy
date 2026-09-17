import SwiftUI

/// 問題の深掘りシート — タップで開く質問フォーム
struct DeepDiveSheetView: View {
    let problem: ProblemType
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var appState: AppState
    @StateObject private var memoryStore = MemoryStore.shared
    @State private var selectedAnswers: [String: Set<String>] = [:]
    @State private var memoryText: String = ""
    @State private var showDeleteAlert = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    // ヘッダー
                    VStack(alignment: .center, spacing: 12) {
                        Text(problem.icon)
                            .font(.system(size: 48))

                        Text(problem.displayName)
                            .font(.title2.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.label)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 16)

                    Divider()
                        .padding(.horizontal, 20)

                    // 共通質問: どのくらい前からこの問題がある？
                    questionSection(question: DeepDiveQuestionsData.commonDurationQuestion)

                    // 問題固有の質問
                    ForEach(Array(DeepDiveQuestionsData.questions(for: problem).enumerated()), id: \.offset) { _, questionData in
                        questionSection(question: questionData)
                    }

                    // Tell Anicca セクション
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text(String(localized: "deep_dive_tell_anicca_title"))
                                .font(.headline)
                                .foregroundStyle(AppTheme.Colors.label)
                            Spacer()
                            if !memoryText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                Button(action: saveMemory) {
                                    Text(String(localized: "common_save"))
                                        .font(.subheadline.weight(.medium))
                                        .foregroundStyle(AppTheme.Colors.buttonSelected)
                                }
                            }
                        }

                        Text(String(localized: "deep_dive_tell_anicca_subtitle"))
                            .font(.caption)
                            .foregroundStyle(AppTheme.Colors.secondaryLabel)

                        TextEditor(text: $memoryText)
                            .frame(minHeight: 100)
                            .padding(12)
                            .background(AppTheme.Colors.cardBackground)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 24)

                    // 保存ボタン
                    PrimaryButton(
                        title: String(localized: "mypath_deepdive_save"),
                        style: .primary
                    ) {
                        saveAnswers()
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 24)

                    Divider()
                        .padding(.horizontal, 20)
                        .padding(.top, 24)

                    // 削除ボタン
                    Button(role: .destructive, action: { showDeleteAlert = true }) {
                        HStack {
                            Image(systemName: "trash")
                            Text(String(localized: "mypath_deepdive_delete"))
                        }
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.red)
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 16)
                    .alert(String(localized: "mypath_deepdive_delete_confirm_title"), isPresented: $showDeleteAlert) {
                        Button(String(localized: "common_cancel"), role: .cancel) { }
                        Button(String(localized: "common_delete"), role: .destructive) {
                            deleteProblem()
                        }
                    } message: {
                        Text(String(localized: "mypath_deepdive_delete_confirm_message"))
                    }
                }
                .padding(.bottom, 40)
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: { dismiss() }) {
                        Image(systemName: "xmark")
                            .foregroundStyle(AppTheme.Colors.secondaryLabel)
                    }
                }
            }
            .background(AppBackground())
            .onAppear {
                memoryText = memoryStore.memory(for: problem)?.text ?? ""
                let details = appState.userProfile.problemDetails
                if let commonAnswers = details["common_duration"] {
                    selectedAnswers[DeepDiveQuestionsData.commonDurationQuestion.questionKey] = Set(commonAnswers)
                }
                for questionData in DeepDiveQuestionsData.questions(for: problem) {
                    if let answers = details[questionData.questionKey] {
                        selectedAnswers[questionData.questionKey] = Set(answers)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func questionSection(question: DeepDiveQuestion) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(String(localized: String.LocalizationValue(stringLiteral: question.questionKey)))
                .font(.headline)
                .foregroundStyle(AppTheme.Colors.label)

            FlowLayout(spacing: 12) {
                ForEach(question.optionKeys, id: \.self) { optionKey in
                    let questionKey = question.questionKey
                    let isSelected = selectedAnswers[questionKey]?.contains(optionKey) ?? false
                    Button {
                        if selectedAnswers[questionKey] == nil {
                            selectedAnswers[questionKey] = []
                        }
                        let isDurationQuestion = question.questionKey == DeepDiveQuestionsData.commonDurationQuestion.questionKey
                        if isDurationQuestion {
                            selectedAnswers[questionKey] = [optionKey]
                        } else {
                            if isSelected {
                                selectedAnswers[questionKey]?.remove(optionKey)
                            } else {
                                selectedAnswers[questionKey]?.insert(optionKey)
                            }
                        }
                    } label: {
                        Text(String(localized: String.LocalizationValue(stringLiteral: optionKey)))
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
            }
        }
        .padding(.horizontal, 20)
    }

    private func saveAnswers() {
        var profile = appState.userProfile
        var details: [String: [String]] = profile.problemDetails
        if let commonAnswers = selectedAnswers[DeepDiveQuestionsData.commonDurationQuestion.questionKey] {
            details["common_duration"] = Array(commonAnswers)
        }
        for questionData in DeepDiveQuestionsData.questions(for: problem) {
            if let answers = selectedAnswers[questionData.questionKey] {
                details[questionData.questionKey] = Array(answers)
            }
        }
        profile.problemDetails = details
        appState.updateUserProfile(profile, sync: true)
        dismiss()
    }

    private func saveMemory() {
        memoryStore.save(text: memoryText, for: problem)
    }

    private func deleteProblem() {
        var profile = appState.userProfile
        profile.problems.removeAll { $0 == problem.rawValue }
        appState.updateUserProfile(profile, sync: true)

        Task {
            await ProblemNotificationScheduler.shared.cancelAllNotifications()
            await ProblemNotificationScheduler.shared.scheduleNotifications(for: profile.problems)
        }
        dismiss()
    }
}
