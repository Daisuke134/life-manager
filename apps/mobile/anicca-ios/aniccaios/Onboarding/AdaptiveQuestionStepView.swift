import SwiftUI

/// The same single-question card language as StrugglesStepView (round one).
struct AdaptiveQuestionStepView: View {
    let question: OnboardingQuestion
    let next: () -> Void
    @EnvironmentObject private var appState: AppState
    @State private var selected: Set<String> = []
    @State private var useBirthDate = false
    @State private var birthDate = Calendar.current.date(byAdding: .year, value: -25, to: Date()) ?? Date()
    @State private var didChooseDate = false

    private var options: [String] { question.options(answers: appState.personalizationProfile.answers) }
    private var isValid: Bool {
        question == .birthContext && useBirthDate ? didChooseDate : !selected.isEmpty
    }

    var body: some View {
        OnboardingPage(alignment: .leading) {
            Text("Anicca").font(.system(.title, design: .serif))
            Spacer(minLength: 12)
            Text(NSLocalizedString("adaptive_\(question.rawValue)_title", comment: ""))
                .font(AppTheme.Typography.onboardingTitle)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("onboarding-\(question.rawValue)-title")
            Text(NSLocalizedString(question.allowsMultiple ? "adaptive_choose_many" : "adaptive_choose_one", comment: ""))
                .font(.subheadline).foregroundStyle(AppTheme.Colors.secondaryLabel)
                .fixedSize(horizontal: false, vertical: true)
            if question == .birthContext {
                birthInput
            } else {
                optionRows
            }
            if question == .priorAttempts {
                Text(String(localized: "adaptive_prior_attempts_hint"))
                    .font(.caption).foregroundStyle(AppTheme.Colors.secondaryLabel)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 12)
        } footer: {
            VStack(spacing: 10) {
                PrimaryButton(title: String(localized: "common_continue"), isEnabled: isValid) { save(skipped: false) }
                    .accessibilityIdentifier("onboarding-\(question.rawValue)-continue")
                if question == .birthContext {
                    Button(String(localized: "adaptive_skip")) { save(skipped: true) }
                        .foregroundStyle(AppTheme.Colors.secondaryLabel)
                        .accessibilityIdentifier("onboarding-birth_context-skip")
                }
            }
        }
        .onAppear {
            let answers = appState.personalizationProfile.answers
            selected = Set(answers.ids(for: question))
            if let saved = answers.birthDate {
                birthDate = saved
                useBirthDate = true
                didChooseDate = true
            }
        }
    }

    private var optionRows: some View {
        VStack(spacing: 12) {
            ForEach(options, id: \.self) { option in
                Button { toggle(option) } label: {
                    HStack(spacing: 14) {
                        Text(NSLocalizedString("adaptive_\(question.rawValue)_\(option)", comment: ""))
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 8)
                        Image(systemName: selected.contains(option) ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(selected.contains(option) ? AppTheme.Colors.accent : AppTheme.Colors.secondaryLabel)
                    }
                    .padding(18)
                    .selectionCard(isSelected: selected.contains(option))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("onboarding-\(question.rawValue)-\(option)")
                .accessibilityAddTraits(selected.contains(option) ? .isSelected : [])
            }
        }
    }

    private var birthInput: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(String(localized: "adaptive_birth_privacy"))
                .font(.subheadline).foregroundStyle(AppTheme.Colors.secondaryLabel)
                .fixedSize(horizontal: false, vertical: true)
            Picker(String(localized: "adaptive_birth_context_title"), selection: $useBirthDate) {
                Text(String(localized: "adaptive_zodiac")).tag(false)
                Text(String(localized: "adaptive_birth_date")).tag(true)
            }
            .pickerStyle(.segmented)
            if useBirthDate {
                DatePicker(String(localized: "adaptive_birth_date"), selection: $birthDate,
                           in: ...Date(), displayedComponents: .date)
                    .datePickerStyle(.graphical)
                    .onChange(of: birthDate) { _ in didChooseDate = true }
                    .accessibilityIdentifier("onboarding-birth-date")
            } else {
                optionRows
            }
        }
    }

    private func toggle(_ option: String) {
        if question.allowsMultiple {
            if selected.contains(option) { selected.remove(option) }
            else if option == question.exclusiveOption { selected = [option] }
            else {
                if let exclusive = question.exclusiveOption { selected.remove(exclusive) }
                selected.insert(option)
            }
        } else { selected = [option] }
    }

    private func save(skipped: Bool) {
        var profile = appState.personalizationProfile
        var answers = profile.answers
        if question == .birthContext {
            answers.setBirthContext(
                birthDate: !skipped && useBirthDate ? birthDate : nil,
                zodiacIDs: skipped ? [] : options.filter { selected.contains($0) })
        } else {
            answers.set(question, ids: options.filter { selected.contains($0) })
            if question == .priorAttempts { answers.values.removeValue(forKey: OnboardingQuestion.priorHelpfulness.rawValue) }
        }
        profile.adaptiveAnswers = answers
        appState.updatePersonalizationProfile(profile)
        next()
    }
}
