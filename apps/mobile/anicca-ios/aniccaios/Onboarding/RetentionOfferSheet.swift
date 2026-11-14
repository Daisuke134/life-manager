import SwiftUI
import RevenueCat

/// Shown once when a purchase is cancelled, with the real retention product price.
struct RetentionOfferSheet: View {
    var flowID: String = "onboarding"
    let onAccepted: (CustomerInfo) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var retentionPackage: Package?
    @State private var isPurchasing = false
    @State private var errorMessage: String?
    @State private var loadFailed = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    Image(systemName: "gift")
                        .font(.system(size: 40, weight: .ultraLight))
                        .foregroundStyle(AppTheme.Colors.accent)
                        .accessibilityHidden(true)
                    Text(String(localized: "retention_title"))
                        .font(.system(.largeTitle, design: .serif))
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                    Text(String(localized: "retention_subtitle"))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)

                    if let package = retentionPackage {
                        VStack(spacing: 8) {
                            Text(String(localized: "paywall_b_plan_yearly"))
                                .font(.subheadline)
                            Text(String(format: NSLocalizedString("paywall_plan_price_yearly", comment: ""), package.localizedPriceString))
                                .font(.system(.title, design: .serif).weight(.semibold))
                                .fixedSize(horizontal: false, vertical: true)
                            Text(String(format: NSLocalizedString("retention_renewal_disclosure", comment: ""), package.localizedPriceString))
                                .font(.footnote)
                                .multilineTextAlignment(.center)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(20)
                        .selectionCard(isSelected: true)
                    } else if loadFailed {
                        Text(String(localized: "paywall_b_load_failed"))
                            .font(.subheadline)
                            .fixedSize(horizontal: false, vertical: true)
                        Button(String(localized: "paywall_b_retry")) {
                            Task { await loadOffer() }
                        }
                    } else {
                        ProgressView()
                    }

                    Label(String(localized: "retention_bullet_features"), systemImage: "checkmark.circle.fill")
                        .font(.subheadline)
                        .foregroundStyle(AppTheme.Colors.accent)
                    PrimaryButton(
                        title: String(localized: "retention_cta_accept"),
                        isEnabled: retentionPackage != nil,
                        isLoading: isPurchasing
                    ) {
                        Task { await acceptOffer() }
                    }
                    .accessibilityIdentifier("retention-accept")

                    HStack(spacing: 16) {
                        Link(String(localized: "paywall_plan_terms"), destination: AppConfig.termsURL)
                        Link(String(localized: "paywall_plan_privacy"), destination: AppConfig.privacyURL)
                    }
                    .font(.footnote)
                    .frame(minHeight: 44)
                }
                .padding(24)
            }
            .background(AppBackground())
            .foregroundStyle(AppTheme.Colors.label)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(String(localized: "common_close")) { dismiss() }
                        .accessibilityIdentifier("retention-close")
                }
            }
        }
        .tint(AppTheme.Colors.accent)
        .analyticsScreen(.retentionOffer, flowID: flowID)
        .task { await loadOffer() }
        .alert(String(localized: "common_error"), isPresented: Binding(
            get: { errorMessage != nil },
            set: { if !$0 { errorMessage = nil } }
        )) {
            Button(String(localized: "common_ok")) { errorMessage = nil }
        } message: {
            Text(errorMessage ?? "")
        }
    }

    @MainActor
    private func loadOffer() async {
        loadFailed = false
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

    @MainActor
    private func acceptOffer() async {
        guard let pkg = retentionPackage else { return }
        isPurchasing = true
        defer { isPurchasing = false }
        do {
            AnalyticsManager.shared.trackPurchaseStarted(package: pkg, offeringID: "anicca_retention", flowID: flowID)
            let result = try await Purchases.shared.purchase(package: pkg)
            if !result.userCancelled {
                AnalyticsManager.shared.observePurchase(package: pkg, transaction: result.transaction, customerInfo: result.customerInfo, flowID: flowID)
                onAccepted(result.customerInfo)
                dismiss()
            } else {
                AnalyticsManager.shared.trackPurchaseResult("cancelled", productID: pkg.storeProduct.productIdentifier, flowID: flowID)
            }
        } catch {
            if let rcError = error as? RevenueCat.ErrorCode, rcError == .purchaseCancelledError {
                AnalyticsManager.shared.trackPurchaseResult("cancelled", productID: pkg.storeProduct.productIdentifier, flowID: flowID)
            } else {
                AnalyticsManager.shared.trackPurchaseResult(
                    "failed",
                    productID: pkg.storeProduct.productIdentifier,
                    flowID: flowID,
                    errorCode: String((error as NSError).code)
                )
            }
            errorMessage = error.localizedDescription
        }
    }
}
