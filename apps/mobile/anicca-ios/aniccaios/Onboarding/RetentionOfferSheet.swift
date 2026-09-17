import SwiftUI
import RevenueCat

/// Retention Offer Sheet (Will / Adam Lyttle pattern)
/// Triggered when user cancels Apple Pay sheet during paywall purchase.
/// $44.99/year (25% OFF vs $59.99). Single CTA: Accept Offer. No decline button.
/// Shown at most once per session (gated by parent's hasShownRetention flag).
struct RetentionOfferSheet: View {
    let onAccepted: (CustomerInfo) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var retentionPackage: Package?
    @State private var isPurchasing = false
    @State private var errorMessage: String?
    @State private var loadFailed = false

    var body: some View {
        VStack(spacing: 24) {
            Spacer().frame(height: 16)

            Text("🎁")
                .font(.system(size: 64))

            Text(String(localized: "retention_title"))
                .font(.system(size: 28, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.label)

            Text(String(localized: "retention_subtitle"))
                .font(.system(size: 16))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            // Price card
            VStack(spacing: 12) {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(retentionPackage?.storeProduct.localizedPriceString ?? "$44.99")
                        .font(.system(size: 36, weight: .heavy))
                        .foregroundColor(AppTheme.Colors.label)
                    Text("/ \(String(localized: "retention_per_year"))")
                        .font(.system(size: 18, weight: .medium))
                        .foregroundColor(.secondary)
                }

                Text(String(localized: "retention_discount_badge"))
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .background(Color.green)
                    .clipShape(Capsule())
            }
            .padding(.vertical, 20)
            .frame(maxWidth: .infinity)
            .background(AppTheme.Colors.buttonUnselected)
            .clipShape(RoundedRectangle(cornerRadius: 20))
            .padding(.horizontal, 24)

            // Bullets
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Text(String(localized: "retention_bullet_cancel"))
                        .font(.system(size: 15))
                        .foregroundStyle(AppTheme.Colors.label)
                }
                HStack(spacing: 10) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Text(String(localized: "retention_bullet_features"))
                        .font(.system(size: 15))
                        .foregroundStyle(AppTheme.Colors.label)
                }
            }

            Spacer()

            Button {
                Task { await acceptOffer() }
            } label: {
                ZStack {
                    Text(String(localized: "retention_cta_accept"))
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(.white)
                        .opacity(isPurchasing ? 0 : 1)
                    if isPurchasing {
                        ProgressView().tint(.white)
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 56)
                .background(AppTheme.Colors.label)
                .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .accessibilityIdentifier("retention-accept")
            .disabled(isPurchasing || retentionPackage == nil)
            .padding(.horizontal, 24)
            .padding(.bottom, 32)
        }
        .background(AppBackground())
        .task { await loadOffer() }
        .alert("Error", isPresented: .constant(errorMessage != nil)) {
            Button("OK") { errorMessage = nil }
        } message: {
            Text(errorMessage ?? "")
        }
    }

    private func loadOffer() async {
        do {
            let offerings = try await Purchases.shared.offerings()
            if let pkg = offerings.offering(identifier: "anicca_retention")?.annual {
                retentionPackage = pkg
            } else {
                loadFailed = true
            }
        } catch {
            loadFailed = true
            errorMessage = error.localizedDescription
        }
    }

    private func acceptOffer() async {
        guard let pkg = retentionPackage else { return }
        isPurchasing = true
        defer { isPurchasing = false }
        do {
            let result = try await Purchases.shared.purchase(package: pkg)
            if !result.userCancelled {
                AnalyticsManager.shared.track(.onboardingPaywallPurchased)
                onAccepted(result.customerInfo)
                dismiss()
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
