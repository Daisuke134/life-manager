import SwiftUI

struct PaywallPrimerStepView: View {
    let next: () -> Void
    @State private var hasTracked = false

    private let features: [(icon: String, key: String)] = [
        ("checkmark.circle.fill", "paywall_primer_feature1"),
        ("bell.badge.fill", "paywall_primer_feature2"),
        ("xmark.circle", "paywall_primer_feature3")
    ]

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                Text(String(localized: "paywall_primer_title"))
                    .font(.system(.largeTitle, design: .serif))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                Text(String(localized: "paywall_primer_subtitle"))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(features, id: \.key) { feature in
                        Label(String(localized: String.LocalizationValue(feature.key)), systemImage: feature.icon)
                            .font(.body)
                            .foregroundStyle(AppTheme.Colors.label)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(20)
                .background(AppTheme.Colors.cardBackground.opacity(0.8))
                .clipShape(RoundedRectangle(cornerRadius: 16))
                PrimaryButton(title: String(localized: "common_continue"), action: next)
                    .accessibilityIdentifier("paywall-primer-cta")
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 64)
        }
        .foregroundStyle(AppTheme.Colors.label)
        .background(AppBackground())
        .onAppear {
            guard !hasTracked else { return }
            hasTracked = true
            AnalyticsManager.shared.track(.paywallPrimerViewed)
        }
    }
}
