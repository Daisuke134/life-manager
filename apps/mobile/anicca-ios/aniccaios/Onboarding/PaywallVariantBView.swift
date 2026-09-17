import SwiftUI
import RevenueCat

/// Variant B paywall — CRO optimized design for RevenueCat Experiments A/B
/// Offering swap is handled server-side by RevenueCat; this view always renders the `current` offering.
struct PaywallVariantBView: View {
    let variant: String
    let onPurchaseSuccess: (CustomerInfo) -> Void
    let onDismiss: () -> Void

    @EnvironmentObject private var appState: AppState
    @State private var selectedPackage: Package?
    @State private var isPurchasing = false
    @State private var errorMessage: String?
    @State private var hasTracked = false
    @State private var hasShownRetention = false
    @State private var showRetention = false
    @State private var showReloadAfterTimeout = false

    private var offering: Offering? { appState.cachedOffering }
    private var packages: [Package] { offering?.availablePackages ?? [] }
    private var yearlyPackage: Package? { packages.first { $0.packageType == .annual } }
    private var monthlyPackage: Package? { packages.first { $0.packageType == .monthly } }
    // 2026-07-03 Dais: 買い切り(lifetime)は日本語話者にのみ表示する。
    // 旧実装は StoreKit の storefront 国(JPN)で判定していたが、
    // storefront は async 取得で初期値が空 → レースで非表示になるバグがあった。
    // 端末の優先言語で判定し (UserProfile / QuoteProvider と同一パターン)、非同期依存を撤廃する。
    private var isJapanese: Bool {
        (Locale.preferredLanguages.first ?? "en").lowercased().hasPrefix("ja")
    }
    private var lifetimePackage: Package? {
        guard isJapanese else { return nil }
        return packages.first { $0.packageType == .lifetime }
    }

    private var savePct: Int? {
        guard let yearly = yearlyPackage, let monthly = monthlyPackage else { return nil }
        let yearlyPrice = (yearly.storeProduct.price as NSDecimalNumber).doubleValue
        let monthlyPrice = (monthly.storeProduct.price as NSDecimalNumber).doubleValue
        guard monthlyPrice > 0 else { return nil }
        return Int((1.0 - yearlyPrice / (monthlyPrice * 12.0)) * 100)
    }

    private var dailyPrice: String? {
        guard let yearly = yearlyPackage else { return nil }
        let price = (yearly.storeProduct.price as NSDecimalNumber).doubleValue / 365.0
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.locale = Locale.current
        formatter.currencyCode = yearly.storeProduct.currencyCode
        formatter.maximumFractionDigits = 2
        return formatter.string(from: NSNumber(value: price))
    }

    // 2026-06-23 Dais: 無料トライアル全廃（ASC からも introductory offer を削除）。
    private var hasTrialEligibility: Bool { false }

    var body: some View {
        VStack(spacing: 12) {
            heroSection
            featureList

            if packages.isEmpty {
                VStack(spacing: 16) {
                    ProgressView()
                    if showReloadAfterTimeout {
                        Text(String(localized: "paywall_b_load_failed"))
                            .font(.system(size: 14))
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 24)
                        Button(String(localized: "paywall_b_retry")) {
                            Task { await SubscriptionManager.shared.refreshOfferings() }
                        }
                        .font(.system(size: 16, weight: .semibold))
                        Button(String(localized: "paywall_plan_restore")) { restorePurchases() }
                            .font(.system(size: 14))
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.top, 40)
                .onAppear { scheduleReloadTimeout() }
                Spacer()
            } else {
                planCards
                ctaSection
            }
        }
        .background(AppBackground())
        .onAppear {
            if !hasTracked {
                hasTracked = true
                AnalyticsManager.shared.track(.paywallPlanSelectionViewed)
                AnalyticsManager.shared.trackPaywallViewed()
            }
            if selectedPackage == nil {
                selectedPackage = yearlyPackage ?? monthlyPackage
            }
        }
        .sheet(isPresented: $showRetention) {
            RetentionOfferSheet { customerInfo in
                showRetention = false
                onPurchaseSuccess(customerInfo)
            }
        }
    }

    // MARK: - Sections

    private var heroSection: some View {
        VStack(spacing: 8) {
            Text(String(localized: "paywall_b_title"))
                .font(.system(size: 28, weight: .bold))
                .foregroundStyle(AppTheme.Colors.label)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
                .padding(.top, 32)

            Text(String(localized: "paywall_b_subtitle"))
                .font(.system(size: 15))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
        }
    }

    private var featureList: some View {
        VStack(alignment: .leading, spacing: 8) {
            featureRow(String(localized: "paywall_b_feature_nudges"))
            featureRow(String(localized: "paywall_b_feature_personalized"))
            featureRow(String(localized: "paywall_b_feature_cancel"))
        }
        .padding(.horizontal, 32)
    }

    private var planCards: some View {
        ScrollView {
            VStack(spacing: 12) {
                // 並び順 2026-06-23 Dais: 月 → 年 → 買い切り
                if let monthly = monthlyPackage {
                    planCard(
                        package: monthly,
                        priceLabel: monthly.localizedPriceString + String(localized: "paywall_b_per_month"),
                        badge: trialBadge(for: monthly),
                        dailyPriceLabel: nil
                    )
                }

                if let yearly = yearlyPackage {
                    planCard(
                        package: yearly,
                        priceLabel: yearly.localizedPriceString + String(localized: "paywall_b_per_year"),
                        badge: trialBadge(for: yearly) ?? String(localized: "paywall_plan_yearly_badge"),
                        dailyPriceLabel: dailyPrice.map {
                            String(format: NSLocalizedString("paywall_b_daily_price", comment: ""), $0)
                        }
                    )
                }

                if let lifetime = lifetimePackage {
                    planCard(
                        package: lifetime,
                        priceLabel: lifetime.localizedPriceString + String(localized: "paywall_b_per_lifetime"),
                        badge: String(localized: "paywall_b_lifetime_badge"),
                        dailyPriceLabel: nil
                    )
                }
            }
            .padding(.horizontal, 24)
            .padding(.top, 8)
        }
    }

    private func trialBadge(for package: Package) -> String? {
        guard hasTrialEligibility else { return nil }
        guard package.packageType == .annual || package.packageType == .monthly else { return nil }
        return String(localized: "paywall_b_trial_badge")
    }

    private var trustText: String {
        guard hasTrialEligibility, let pkg = selectedPackage else {
            return String(localized: "paywall_b_trust_no_trial")
        }
        return String(format: NSLocalizedString("paywall_b_trust_trial", comment: ""), pkg.localizedPriceString)
    }

    private var ctaSection: some View {
        VStack(spacing: 10) {
            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .padding(.horizontal, 24)
            }

            Button { purchase() } label: {
                Group {
                    if isPurchasing {
                        ProgressView().tint(.white)
                    } else {
                        Text(String(localized: hasTrialEligibility ? "paywall_b_cta_trial" : "paywall_b_cta_no_trial"))
                    }
                }
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 56)
                .background(selectedPackage != nil ? AppTheme.Colors.accent : AppTheme.Colors.accent.opacity(0.5))
                .clipShape(RoundedRectangle(cornerRadius: 28))
            }
            .disabled(selectedPackage == nil || isPurchasing)
            .accessibilityIdentifier("paywall-plan-cta")
            .padding(.horizontal, 24)

            Text(String(localized: "paywall_b_review"))
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(.secondary)
                .italic()
                .padding(.horizontal, 24)

            Text(trustText)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            HStack(spacing: 24) {
                Button(String(localized: "paywall_plan_restore")) { restorePurchases() }
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("paywall-restore")
            }

            HStack(spacing: 8) {
                Link(String(localized: "paywall_plan_terms"), destination: AppConfig.termsURL)
                Text("·").foregroundStyle(.secondary)
                Link(String(localized: "paywall_plan_privacy"), destination: AppConfig.privacyURL)
            }
            .font(.system(size: 12))
            .foregroundStyle(.secondary)
        }
        .padding(.bottom, 32)
    }

    // MARK: - Components

    @ViewBuilder
    private func featureRow(_ text: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 16))
                .foregroundStyle(AppTheme.Colors.accent)
                .frame(width: 24)
            Text(text)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(AppTheme.Colors.label)
        }
    }

    @ViewBuilder
    private func planCard(
        package: Package,
        priceLabel: String,
        badge: String?,
        dailyPriceLabel: String?
    ) -> some View {
        let isSelected = selectedPackage?.identifier == package.identifier

        Button { selectedPackage = package } label: {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        Text(localizedPlanTitle(for: package))
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundStyle(AppTheme.Colors.label)

                        if let badge {
                            Text(badge)
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(.white)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(AppTheme.Colors.accent)
                                .clipShape(Capsule())
                        }
                    }

                    Text(priceLabel)
                        .font(.system(size: 14))
                        .foregroundStyle(.secondary)

                    if let dailyPriceLabel {
                        Text(dailyPriceLabel)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(AppTheme.Colors.accent)
                    }
                }

                Spacer()

                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 24))
                    .foregroundStyle(isSelected ? AppTheme.Colors.accent : .secondary)
            }
            .padding(16)
            .background(isSelected ? AppTheme.Colors.accent.opacity(0.1) : AppTheme.Colors.buttonUnselected)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(isSelected ? AppTheme.Colors.accent : Color.clear, lineWidth: 2)
            )
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("paywall-plan-\(package.packageType.rawValue)")
    }

    private func localizedPlanTitle(for package: Package) -> String {
        switch package.packageType {
        case .annual: return String(localized: "paywall_b_plan_yearly")
        case .monthly: return String(localized: "paywall_b_plan_monthly")
        case .weekly: return String(localized: "paywall_b_plan_weekly")
        case .lifetime: return String(localized: "paywall_b_plan_lifetime")
        default: return package.storeProduct.localizedTitle
        }
    }

    // MARK: - Actions

    private func scheduleReloadTimeout() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
            if packages.isEmpty { showReloadAfterTimeout = true }
            Task { await SubscriptionManager.shared.refreshOfferings() }
        }
    }

    private func purchase() {
        guard let package = selectedPackage else { return }
        isPurchasing = true
        errorMessage = nil

        Task {
            do {
                let result = try await Purchases.shared.purchase(package: package)
                if !result.userCancelled {
                    AnalyticsManager.shared.track(.onboardingPaywallPurchased)
                    await MainActor.run {
                        isPurchasing = false
                        onPurchaseSuccess(result.customerInfo)
                    }
                } else {
                    await MainActor.run {
                        isPurchasing = false
                        if !hasShownRetention {
                            hasShownRetention = true
                            showRetention = true
                        }
                    }
                }
            } catch {
                await MainActor.run {
                    isPurchasing = false
                    if let rcError = error as? RevenueCat.ErrorCode,
                       rcError == .purchaseCancelledError {
                        if !hasShownRetention {
                            hasShownRetention = true
                            showRetention = true
                        }
                    } else {
                        errorMessage = error.localizedDescription
                    }
                }
            }
        }
    }

    private func restorePurchases() {
        isPurchasing = true
        errorMessage = nil
        Task {
            do {
                let customerInfo = try await Purchases.shared.restorePurchases()
                await MainActor.run {
                    isPurchasing = false
                    if customerInfo.entitlements[AppConfig.revenueCatEntitlementId]?.isActive == true {
                        onPurchaseSuccess(customerInfo)
                    }
                }
            } catch {
                await MainActor.run {
                    isPurchasing = false
                    errorMessage = error.localizedDescription
                }
            }
        }
    }
}
