import SwiftUI
import StoreKit
import RevenueCat

// MARK: - S2 Age

struct AgeRangeStepView: View {
    let next: () -> Void
    @EnvironmentObject private var appState: AppState
    private let options = ["under_18", "18_24", "25_34", "35_44", "45_54", "55_plus"]
    private let labelKeys = ["age_under_18", "age_18_24", "age_25_34", "age_35_44", "age_45_54", "age_55_plus"]

    var body: some View {
        VStack(spacing: 16) {
            Spacer().frame(height: 40)
            Text(String(localized: "onboarding_age_title"))
                .font(.system(size: 32, weight: .bold))
                .foregroundStyle(AppTheme.Colors.label)

            VStack(spacing: 12) {
                ForEach(Array(options.enumerated()), id: \.offset) { idx, key in
                    Button {
                        var profile = appState.userProfile
                        profile.ageRange = key
                        appState.updateUserProfile(profile, sync: true)
                        next()
                    } label: {
                        Text(String(localized: String.LocalizationValue(labelKeys[idx])))
                            .font(.system(size: 18, weight: .medium))
                            .foregroundStyle(AppTheme.Colors.label)
                            .frame(maxWidth: .infinity).frame(height: 56)
                            .background(AppTheme.Colors.buttonUnselected)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 24)
            Spacer()
        }
        .background(AppBackground())
    }
}

// MARK: - S4 Goal

struct GoalStepView: View {
    let next: () -> Void
    @EnvironmentObject private var appState: AppState
    @State private var selected: String? = nil

    private let options: [(key: String, emoji: String, locKey: String)] = [
        ("break_habit", "🚫", "goal_break_habit"),
        ("build_discipline", "💪", "goal_build_discipline"),
        ("reduce_anxiety", "🧘", "goal_reduce_anxiety"),
        ("sleep_better", "😴", "goal_sleep_better"),
        ("focus_more", "🎯", "goal_focus_more"),
        ("feel_peace", "☮️", "goal_feel_peace")
    ]

    var body: some View {
        VStack(spacing: 16) {
            Spacer().frame(height: 40)
            Text(String(localized: "onboarding_goal_title"))
                .font(.system(size: 28, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.horizontal, 24)

            ScrollView {
                VStack(spacing: 12) {
                    ForEach(options, id: \.key) { opt in
                        Button {
                            selected = opt.key
                            var profile = appState.userProfile
                            profile.goals = [opt.key]
                            appState.updateUserProfile(profile, sync: true)
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { next() }
                        } label: {
                            HStack {
                                Text(opt.emoji).font(.system(size: 24))
                                Text(String(localized: String.LocalizationValue(opt.locKey)))
                                    .font(.system(size: 17, weight: .medium))
                                    .foregroundStyle(AppTheme.Colors.label)
                                Spacer()
                            }
                            .padding(.horizontal, 20)
                            .frame(maxWidth: .infinity).frame(height: 64)
                            .background(selected == opt.key ? AppTheme.Colors.accent.opacity(0.2) : AppTheme.Colors.buttonUnselected)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 24)
            }
            Spacer()
        }
        .background(AppBackground())
    }
}

// MARK: - S7 Tinder Pain Cards

struct TinderPainCardsView: View {
    let next: () -> Void

    private let cardKeys = [
        "tinder_card_1", "tinder_card_2", "tinder_card_3", "tinder_card_4", "tinder_card_5"
    ]
    @State private var index = 0
    @State private var offset: CGSize = .zero

    var body: some View {
        VStack {
            Spacer().frame(height: 24)
            Text(String(localized: "onboarding_tinder_title"))
                .font(.system(size: 24, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.horizontal, 24)

            Text(String(localized: "onboarding_tinder_subtitle"))
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
                .padding(.top, 8)

            Spacer()

            if index < cardKeys.count {
                ZStack {
                    Text(String(localized: String.LocalizationValue(cardKeys[index])))
                        .font(.system(size: 22, weight: .semibold))
                        .multilineTextAlignment(.center)
                        .foregroundStyle(AppTheme.Colors.label)
                        .padding(32)
                        .frame(maxWidth: .infinity, minHeight: 280)
                        .background(AppTheme.Colors.buttonUnselected)
                        .clipShape(RoundedRectangle(cornerRadius: 20))
                        .padding(.horizontal, 24)
                        .offset(offset)
                        .rotationEffect(.degrees(Double(offset.width / 20)))
                        .gesture(
                            DragGesture()
                                .onChanged { offset = $0.translation }
                                .onEnded { value in
                                    if value.translation.width > 100 {
                                        AnalyticsManager.shared.track(.tinderPainCardAgreed, properties: ["card": index])
                                        advance()
                                    } else if value.translation.width < -100 {
                                        AnalyticsManager.shared.track(.tinderPainCardDismissed, properties: ["card": index])
                                        advance()
                                    } else {
                                        withAnimation { offset = .zero }
                                    }
                                }
                        )
                }
            }

            Spacer()

            HStack(spacing: 32) {
                Button {
                    AnalyticsManager.shared.track(.tinderPainCardDismissed, properties: ["card": index])
                    advance()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundStyle(.red)
                        .frame(width: 64, height: 64)
                        .background(Color.white)
                        .clipShape(Circle())
                        .shadow(radius: 4)
                }
                Button {
                    AnalyticsManager.shared.track(.tinderPainCardAgreed, properties: ["card": index])
                    advance()
                } label: {
                    Image(systemName: "checkmark")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundStyle(.green)
                        .frame(width: 64, height: 64)
                        .background(Color.white)
                        .clipShape(Circle())
                        .shadow(radius: 4)
                }
            }
            .padding(.bottom, 64)
        }
        .background(AppBackground())
    }

    private func advance() {
        withAnimation {
            offset = .zero
            index += 1
        }
        if index >= cardKeys.count {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { next() }
        }
    }
}

// MARK: - S8 What Tried

struct WhatTriedStepView: View {
    let next: () -> Void
    @EnvironmentObject private var appState: AppState
    @State private var selected: Set<String> = []

    private let options: [(key: String, locKey: String)] = [
        ("willpower", "tried_willpower"),
        ("habit_apps", "tried_habit_apps"),
        ("meditation", "tried_meditation"),
        ("therapy", "tried_therapy"),
        ("journaling", "tried_journaling"),
        ("books", "tried_books"),
        ("nothing", "tried_nothing")
    ]

    var body: some View {
        VStack(spacing: 20) {
            Spacer().frame(height: 40)
            Text(String(localized: "onboarding_what_tried_title"))
                .font(.system(size: 28, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.horizontal, 24)

            ScrollView {
                VStack(spacing: 12) {
                    ForEach(options, id: \.key) { opt in
                        let isSelected = selected.contains(opt.key)
                        Button {
                            if isSelected { selected.remove(opt.key) } else { selected.insert(opt.key) }
                        } label: {
                            HStack {
                                Image(systemName: isSelected ? "checkmark.square.fill" : "square")
                                    .foregroundStyle(isSelected ? AppTheme.Colors.accent : .secondary)
                                Text(String(localized: String.LocalizationValue(opt.locKey)))
                                    .font(.system(size: 17, weight: .medium))
                                    .foregroundStyle(AppTheme.Colors.label)
                                Spacer()
                            }
                            .padding(.horizontal, 20)
                            .frame(maxWidth: .infinity).frame(height: 56)
                            .background(AppTheme.Colors.buttonUnselected)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 24)
            }

            Button {
                next()
            } label: {
                Text(String(localized: "common_continue"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity).frame(height: 56)
                    .background(selected.isEmpty ? AppTheme.Colors.label.opacity(0.4) : AppTheme.Colors.accent)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .disabled(selected.isEmpty)
            .padding(.horizontal, 24)
            .padding(.bottom, 48)
        }
        .background(AppBackground())
    }
}

// MARK: - S9 Stress Slider

struct StressSliderStepView: View {
    let next: () -> Void
    @EnvironmentObject private var appState: AppState
    @State private var value: Double = 5

    var body: some View {
        VStack(spacing: 24) {
            Spacer().frame(height: 40)
            Text(String(localized: "onboarding_stress_title"))
                .font(.system(size: 28, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.horizontal, 24)

            Text("\(Int(value))")
                .font(.system(size: 80, weight: .bold))
                .foregroundStyle(AppTheme.Colors.accent)

            Slider(value: $value, in: 0...10, step: 1)
                .tint(AppTheme.Colors.accent)
                .padding(.horizontal, 32)

            HStack {
                Text(String(localized: "stress_label_calm")).font(.caption).foregroundStyle(.secondary)
                Spacer()
                Text(String(localized: "stress_label_overwhelmed")).font(.caption).foregroundStyle(.secondary)
            }
            .padding(.horizontal, 32)

            Spacer()

            Button { next() } label: {
                Text(String(localized: "common_continue"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity).frame(height: 56)
                    .background(AppTheme.Colors.accent)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 48)
        }
        .background(AppBackground())
    }
}

// MARK: - S10 Social Proof

struct SocialProofStepView: View {
    let next: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Spacer().frame(height: 40)
            Text(String(localized: "onboarding_social_title"))
                .font(.system(size: 32, weight: .bold))
                .foregroundStyle(AppTheme.Colors.label)

            VStack(spacing: 4) {
                HStack(spacing: 2) {
                    ForEach(0..<5) { _ in
                        Image(systemName: "star.fill").foregroundStyle(.yellow)
                    }
                }
                Text(String(localized: "onboarding_social_rating"))
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(.secondary)
            }

            ScrollView {
                VStack(spacing: 16) {
                    testimonial(
                        name: String(localized: "social_name_1"),
                        tag: String(localized: "social_tag_1"),
                        text: String(localized: "social_text_1")
                    )
                    testimonial(
                        name: String(localized: "social_name_2"),
                        tag: String(localized: "social_tag_2"),
                        text: String(localized: "social_text_2")
                    )
                }
                .padding(.horizontal, 24)
            }

            Button { next() } label: {
                Text(String(localized: "common_continue"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity).frame(height: 56)
                    .background(AppTheme.Colors.accent)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 48)
        }
        .background(AppBackground())
    }

    private func testimonial(name: String, tag: String, text: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(name).font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(AppTheme.Colors.label)
                Text("· \(tag)").font(.system(size: 13))
                    .foregroundStyle(.secondary)
            }
            Text(text).font(.system(size: 14))
                .foregroundStyle(AppTheme.Colors.label.opacity(0.85))
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.buttonUnselected)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

// MARK: - S11 Preferred Nudge Times

struct PreferredNudgeTimesView: View {
    let next: () -> Void
    @State private var selected: Set<String> = []

    private let options: [(key: String, locKey: String, icon: String)] = [
        ("morning", "nudge_morning", "sunrise.fill"),
        ("afternoon", "nudge_afternoon", "sun.max.fill"),
        ("evening", "nudge_evening", "moon.stars.fill")
    ]

    var body: some View {
        VStack(spacing: 20) {
            Spacer().frame(height: 40)
            Text(String(localized: "onboarding_nudge_title"))
                .font(.system(size: 28, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.horizontal, 24)

            Text(String(localized: "onboarding_nudge_subtitle"))
                .font(.system(size: 14))
                .foregroundStyle(.secondary)

            VStack(spacing: 12) {
                ForEach(options, id: \.key) { opt in
                    let isSelected = selected.contains(opt.key)
                    Button {
                        if isSelected { selected.remove(opt.key) } else { selected.insert(opt.key) }
                    } label: {
                        HStack {
                            Image(systemName: opt.icon).foregroundStyle(AppTheme.Colors.accent)
                                .frame(width: 28)
                            Text(String(localized: String.LocalizationValue(opt.locKey)))
                                .font(.system(size: 17, weight: .medium))
                                .foregroundStyle(AppTheme.Colors.label)
                            Spacer()
                            Image(systemName: isSelected ? "checkmark.square.fill" : "square")
                                .foregroundStyle(isSelected ? AppTheme.Colors.accent : .secondary)
                        }
                        .padding(.horizontal, 20)
                        .frame(maxWidth: .infinity).frame(height: 64)
                        .background(AppTheme.Colors.buttonUnselected)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 24)

            Spacer()

            Button { next() } label: {
                Text(String(localized: "common_continue"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity).frame(height: 56)
                    .background(AppTheme.Colors.accent)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
                    .opacity(selected.count >= 1 ? 1.0 : 0.5)
            }
            .disabled(selected.count < 1)
            .padding(.horizontal, 24)
            .padding(.bottom, 48)
        }
        .background(AppBackground())
    }
}

// MARK: - S12 Meditation Experience

struct MeditationExperienceStepView: View {
    let next: () -> Void
    private let options: [(key: String, locKey: String)] = [
        ("never", "medit_never"),
        ("few_times", "medit_few_times"),
        ("regularly", "medit_regularly"),
        ("daily", "medit_daily")
    ]

    var body: some View {
        VStack(spacing: 20) {
            Spacer().frame(height: 40)
            Text(String(localized: "onboarding_medit_title"))
                .font(.system(size: 28, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.horizontal, 24)

            VStack(spacing: 12) {
                ForEach(options, id: \.key) { opt in
                    Button {
                        next()
                    } label: {
                        Text(String(localized: String.LocalizationValue(opt.locKey)))
                            .font(.system(size: 17, weight: .medium))
                            .foregroundStyle(AppTheme.Colors.label)
                            .frame(maxWidth: .infinity).frame(height: 56)
                            .background(AppTheme.Colors.buttonUnselected)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 24)
            Spacer()
        }
        .background(AppBackground())
    }
}

// MARK: - S14 Comparison Table

struct ComparisonTableStepView: View {
    let next: () -> Void

    private let rowKeys: [String] = [
        "comparison_row_1", "comparison_row_2", "comparison_row_3", "comparison_row_4"
    ]

    var body: some View {
        VStack(spacing: 20) {
            Spacer().frame(height: 24)
            VStack(spacing: 8) {
                Text("96%")
                    .font(.system(size: 64, weight: .bold))
                    .foregroundStyle(AppTheme.Colors.accent)
                Text(String(localized: "onboarding_comparison_stat"))
                    .font(.system(size: 16, weight: .medium))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(AppTheme.Colors.label)
                    .padding(.horizontal, 24)
            }

            VStack(spacing: 0) {
                HStack {
                    Text("").frame(maxWidth: .infinity, alignment: .leading)
                    Text(String(localized: "comparison_header_without")).font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.secondary).frame(width: 90)
                    Text(String(localized: "comparison_header_anicca")).font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(AppTheme.Colors.accent).frame(width: 90)
                }
                .padding(.horizontal, 16).padding(.vertical, 12)
                .background(AppTheme.Colors.buttonUnselected.opacity(0.5))

                ForEach(rowKeys, id: \.self) { key in
                    HStack {
                        Text(String(localized: String.LocalizationValue(key)))
                            .font(.system(size: 13))
                            .foregroundStyle(AppTheme.Colors.label)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Text("")
                            .frame(width: 90)
                        Image(systemName: "checkmark")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundStyle(.green)
                            .frame(width: 90)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 14)
                    Divider()
                }
            }
            .background(AppTheme.Colors.buttonUnselected.opacity(0.2))
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .padding(.horizontal, 24)

            Spacer()

            Button { next() } label: {
                Text(String(localized: "common_continue"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity).frame(height: 56)
                    .background(AppTheme.Colors.accent)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 48)
        }
        .background(AppBackground())
    }
}

// MARK: - S19 Rating Pre-Prompt

struct RatingPrePromptStepView: View {
    let next: () -> Void
    @State private var awaitingReview = false

    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            Text(String(localized: "onboarding_rating_title"))
                .font(.system(size: 28, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.horizontal, 24)

            HStack(spacing: 4) {
                ForEach(0..<5) { _ in
                    Image(systemName: "star.fill")
                        .font(.system(size: 36))
                        .foregroundStyle(.yellow)
                }
            }

            Spacer()

            Button {
                AnalyticsManager.shared.track(.ratingPromptYesTapped)
                requestStoreReview()
            } label: {
                Text(String(localized: "rating_cta"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity).frame(height: 56)
                    .background(AppTheme.Colors.accent)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 48)
        }
        .background(AppBackground())
        .onAppear { AnalyticsManager.shared.track(.ratingPromptShown) }
        .onReceive(NotificationCenter.default.publisher(
            for: UIApplication.didBecomeActiveNotification
        )) { _ in
            if awaitingReview {
                awaitingReview = false
                next()
            }
        }
    }

    private func requestStoreReview() {
        AnalyticsManager.shared.track(.ratingStoreReviewRequested)
        awaitingReview = true
        if let scene = UIApplication.shared.connectedScenes
            .first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene {
            SKStoreReviewController.requestReview(in: scene)
        }
        // Fallback: system may suppress dialog (3x/year limit) or simulator
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            if self.awaitingReview {
                self.awaitingReview = false
                self.next()
            }
        }
    }
}

// MARK: - PW S2 Value Timeline

struct PaywallValueTimelineStepView: View {
    let next: () -> Void

    private let milestones: [(weekKey: String, textKey: String)] = [
        ("timeline_week_1", "timeline_week_1_text"),
        ("timeline_week_4", "timeline_week_4_text"),
        ("timeline_week_8", "timeline_week_8_text"),
        ("timeline_week_12", "timeline_week_12_text")
    ]

    var body: some View {
        VStack(spacing: 20) {
            Spacer().frame(height: 32)
            Text(String(localized: "paywall_timeline_title"))
                .font(.system(size: 26, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.horizontal, 24)

            ScrollView {
                VStack(spacing: 16) {
                    ForEach(Array(milestones.enumerated()), id: \.offset) { _, m in
                        HStack(alignment: .top, spacing: 16) {
                            VStack {
                                Circle().fill(AppTheme.Colors.accent).frame(width: 12, height: 12)
                                Rectangle().fill(AppTheme.Colors.accent.opacity(0.3)).frame(width: 2)
                            }
                            VStack(alignment: .leading, spacing: 4) {
                                Text(String(localized: String.LocalizationValue(m.weekKey)))
                                    .font(.system(size: 15, weight: .bold))
                                    .foregroundStyle(AppTheme.Colors.accent)
                                Text(String(localized: String.LocalizationValue(m.textKey)))
                                    .font(.system(size: 15))
                                    .foregroundStyle(AppTheme.Colors.label)
                            }
                            Spacer()
                        }
                    }
                }
                .padding(.horizontal, 24)
            }

            Button { next() } label: {
                Text(String(localized: "common_continue"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity).frame(height: 56)
                    .background(AppTheme.Colors.accent)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 48)
        }
        .background(AppBackground())
    }
}

// MARK: - Paywall Flow Container (Soft Paywall — 右上 × で無課金メインへ)

struct PaywallFlowContainer: View {
    let onPurchaseSuccess: (CustomerInfo) -> Void
    let onDismiss: () -> Void
    @State private var step: PaywallStep = .primer
    @EnvironmentObject private var appState: AppState

    var body: some View {
        ZStack(alignment: .topTrailing) {
            AppBackground()

            switch step {
            case .primer:
                PaywallPrimerStepView(next: { step = .planSelection })
            case .planSelection:
                PaywallVariantBView(
                    variant: "b",
                    onPurchaseSuccess: onPurchaseSuccess,
                    onDismiss: onDismiss
                )
            }

            // ソフトペイウォール: 右上に平均サイズの × 。課金せずメイン画面へ。
            // primer / planSelection どちらの段でも常に表示。
            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            .accessibilityIdentifier("paywall-close-button")
            .accessibilityLabel(Text(String(localized: "common_close")))
            .padding(.trailing, 12)
            .padding(.top, 8)
        }
    }
}
