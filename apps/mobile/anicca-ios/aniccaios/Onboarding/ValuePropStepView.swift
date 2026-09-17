import SwiftUI

/// Phase 3: VALUE DEMO — 7-day journey timeline.
struct ValuePropStepView: View {
    let next: () -> Void

    private let days: [(dayKey: String, emoji: String)] = [
        ("onboarding_valueprop_day1", "1"),
        ("onboarding_valueprop_day2", "2"),
        ("onboarding_valueprop_day3", "3"),
        ("onboarding_valueprop_day4", "4"),
        ("onboarding_valueprop_day5", "5"),
        ("onboarding_valueprop_day6", "6"),
        ("onboarding_valueprop_day7", "7")
    ]

    var body: some View {
        VStack(spacing: 0) {
            Text(String(localized: "onboarding_valueprop_title"))
                .font(.system(size: 32, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.top, 40)
                .padding(.bottom, 24)

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(days.enumerated()), id: \.element.dayKey) { index, day in
                        HStack(alignment: .top, spacing: 16) {
                            // Timeline dot and line
                            VStack(spacing: 0) {
                                Circle()
                                    .fill(AppTheme.Colors.accent)
                                    .frame(width: 28, height: 28)
                                    .overlay(
                                        Text(day.emoji)
                                            .font(.system(size: 14, weight: .bold))
                                            .foregroundStyle(.white)
                                    )

                                if index < days.count - 1 {
                                    Rectangle()
                                        .fill(AppTheme.Colors.accent.opacity(0.3))
                                        .frame(width: 2, height: 32)
                                }
                            }

                            Text(String(localized: String.LocalizationValue(day.dayKey)))
                                .font(.system(size: 15, weight: .medium))
                                .foregroundStyle(AppTheme.Colors.label)
                                .padding(.top, 4)

                            Spacer()
                        }
                    }
                }
                .padding(.horizontal, 32)
                .padding(.bottom, 16)
            }

            Spacer()

            Button {
                AnalyticsManager.shared.track(.onboardingValuePropCompleted)
                next()
            } label: {
                Text(String(localized: "onboarding_valueprop_cta"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: 56)
                    .background(AppTheme.Colors.label)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .accessibilityIdentifier("onboarding-valueprop-cta")
            .padding(.horizontal, 24)
            .padding(.bottom, 64)
        }
        .background(AppBackground())
    }
}
