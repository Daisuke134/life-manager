import SwiftUI

/// Phase 5: CONVERT — Step 1: "Try for free", no price shown.
struct PaywallPrimerStepView: View {
    let next: () -> Void
    @State private var hasTracked = false

    private let features: [(icon: String, key: String)] = [
        ("checkmark.circle.fill", "paywall_primer_feature1"),
        ("bell.badge.fill", "paywall_primer_feature2"),
        ("xmark.circle", "paywall_primer_feature3")
    ]

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Text(String(localized: "paywall_primer_title"))
                .font(.system(size: 32, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.horizontal, 24)

            Text(String(localized: "paywall_primer_subtitle"))
                .font(.system(size: 16))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            VStack(alignment: .leading, spacing: 16) {
                ForEach(features, id: \.key) { feature in
                    HStack(spacing: 12) {
                        Image(systemName: feature.icon)
                            .font(.system(size: 20))
                            .foregroundStyle(AppTheme.Colors.accent)
                            .frame(width: 28)

                        Text(String(localized: String.LocalizationValue(feature.key)))
                            .font(.system(size: 16, weight: .medium))
                            .foregroundStyle(AppTheme.Colors.label)
                    }
                }
            }
            .padding(.horizontal, 40)

            Spacer()

            Button {
                next()
            } label: {
                Text(String(localized: "common_continue"))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: 56)
                    .background(AppTheme.Colors.accent)
                    .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .accessibilityIdentifier("paywall-primer-cta")
            .padding(.horizontal, 24)
            .padding(.bottom, 64)
        }
        .background(AppBackground())
        .onAppear {
            guard !hasTracked else { return }
            hasTracked = true
            AnalyticsManager.shared.track(.paywallPrimerViewed)
        }
    }
}
