import SwiftUI
import RevenueCat
import PostHog

/// 2026-10-31 hard-paywall experiment (treatment arm).
/// - Treatment when PostHog flag `paywall-ab-test` == "hard" (or its payload has `hard_paywall: true`),
///   or when the RevenueCat current offering carries metadata `"paywall": "hard"` (RC Experiment arm).
/// - All prices / trial lengths come from the RevenueCat current offering → price tests need no release.
/// - Annual (with trial when eligible) is preselected. Close (X) appears after `closeDelay` seconds.
/// - Tapping X shows ONE retention offer (offering `anicca_retention`, annual package) with full terms.
enum HardPaywallExperiment {
    static let flagKey = "paywall-ab-test"
    static let closeDelay: Double = 3

    static func isTreatment(offering: Offering?) -> Bool {
        if let meta = offering?.metadata["paywall"] as? String, meta.lowercased() == "hard" { return true }
        if let variant = PostHogSDK.shared.getFeatureFlag(flagKey) as? String, variant.lowercased() == "hard" { return true }
        if let payload = PostHogSDK.shared.getFeatureFlagPayload(flagKey) as? [String: Any],
           payload["hard_paywall"] as? Bool == true { return true }
        return false
    }
}

enum PaywallTerms {
    static func periodText(_ period: SubscriptionPeriod?) -> String {
        guard let p = period else { return "" }
        let unit: String
        switch p.unit {
        case .day: unit = p.value == 1 ? L("hp_unit_day", "day") : L("hp_unit_days", "days")
        case .week: unit = p.value == 1 ? L("hp_unit_week", "week") : L("hp_unit_weeks", "weeks")
        case .month: unit = p.value == 1 ? L("hp_unit_month", "month") : L("hp_unit_months", "months")
        case .year: unit = p.value == 1 ? L("hp_unit_year", "year") : L("hp_unit_years", "years")
        @unknown default: unit = ""
        }
        return p.value == 1 ? unit : "\(p.value) \(unit)"
    }

    static func freeTrial(_ product: StoreProduct, eligible: Bool) -> StoreProductDiscount? {
        guard eligible, let intro = product.introductoryDiscount, intro.paymentMode == .freeTrial else { return nil }
        return intro
    }

    /// Billed amount first (most prominent), then trial, period and auto-renew terms (Guideline 3.1.2).
    static func headline(_ product: StoreProduct) -> String {
        "\(product.localizedPriceString) / \(periodText(product.subscriptionPeriod))"
    }

    static func disclosure(_ product: StoreProduct, trial: StoreProductDiscount?) -> String {
        let price = product.localizedPriceString
        let period = periodText(product.subscriptionPeriod)
        if let trial {
            let trialLen = "\(trial.subscriptionPeriod.value) \(periodText(SubscriptionPeriod(value: 1, unit: trial.subscriptionPeriod.unit)))"
            return String(format: L("hp_terms_trial",
                "Free for %1$@, then %2$@ per %3$@. Auto-renews every %3$@ until cancelled. Cancel at least 24 hours before the trial ends to avoid being charged. Manage or cancel anytime in Settings > Apple ID > Subscriptions."),
                trialLen, price, period)
        }
        return String(format: L("hp_terms_no_trial",
            "%1$@ billed every %2$@. Auto-renews until cancelled. Payment is charged to your Apple ID at confirmation. Cancel at least 24 hours before the end of the current period in Settings > Apple ID > Subscriptions."),
            price, period)
    }

    static func L(_ key: String, _ fallback: String) -> String {
        NSLocalizedString(key, value: fallback, comment: "")
    }
}

struct HardPaywallView: View {
    let onPurchaseSuccess: (CustomerInfo) -> Void
    let onDismiss: () -> Void

    @EnvironmentObject private var appState: AppState
    @State private var selected: Package?
    @State private var eligibility: [String: Bool] = [:]
    @State private var isPurchasing = false
    @State private var errorMessage: String?
    @State private var showClose = false
    @State private var showRetention = false
    @State private var tracked = false

    private typealias T = PaywallTerms
    private var packages: [Package] { appState.cachedOffering?.availablePackages ?? [] }
    private var annual: Package? { packages.first { $0.packageType == .annual } }
    private var ordered: [Package] {
        // Copy-the-winner (PAYWALL-PRICING.md): yearly first, weekly second, no monthly on the main screen.
        let order: [PackageType] = [.annual, .weekly]
        return packages.filter { order.contains($0.packageType) }
            .sorted { (order.firstIndex(of: $0.packageType) ?? 9) < (order.firstIndex(of: $1.packageType) ?? 9) }
    }
    private func trial(_ p: Package) -> StoreProductDiscount? {
        T.freeTrial(p.storeProduct, eligible: eligibility[p.storeProduct.productIdentifier] ?? false)
    }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            AppBackground()
            VStack(spacing: 14) {
                Text(T.L("hp_title", "Unlock your full Anicca plan"))
                    .font(.system(size: 28, weight: .bold))
                    .foregroundStyle(AppTheme.Colors.label)
                    .multilineTextAlignment(.center)
                    .padding(.top, 48).padding(.horizontal, 24)
                VStack(alignment: .leading, spacing: 8) {
                    feature(String(localized: "paywall_b_feature_nudges"))
                    feature(String(localized: "paywall_b_feature_personalized"))
                    feature(String(localized: "paywall_b_feature_cancel"))
                }.padding(.horizontal, 32)

                if packages.isEmpty {
                    ProgressView().padding(.top, 32)
                    Button(String(localized: "paywall_b_retry")) {
                        Task { await SubscriptionManager.shared.refreshOfferings() }
                    }.font(.system(size: 15, weight: .semibold))
                    Spacer()
                    footer
                } else {
                    ScrollView {
                        VStack(spacing: 10) { ForEach(ordered, id: \.identifier) { card($0) } }
                            .padding(.horizontal, 24)
                    }
                    cta
                }
            }
            if showClose {
                // 2026-10-31 参謀: retention offer skipped for now; close goes straight to the app.
                Button { onDismiss() } label: {
                    Image(systemName: "xmark").font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(.secondary).frame(width: 44, height: 44).contentShape(Rectangle())
                }
                .accessibilityIdentifier("paywall-close-button")
                .accessibilityLabel(Text(String(localized: "common_close")))
                .padding(.trailing, 12).padding(.top, 8)
                .transition(.opacity)
            }
        }
        .onAppear {
            if !tracked {
                tracked = true
                AnalyticsManager.shared.trackPaywallViewed()
                AnalyticsManager.shared.trackPostHog("paywall_viewed", properties: ["variant": "hard_2026_10_31"])
            }
            if selected == nil { selected = annual ?? ordered.first }
            DispatchQueue.main.asyncAfter(deadline: .now() + HardPaywallExperiment.closeDelay) {
                withAnimation { showClose = true }
            }
        }
        .task(id: packages.map(\.identifier)) {
            if selected == nil || !packages.contains(where: { $0.identifier == selected?.identifier }) {
                selected = annual ?? ordered.first
            }
            let result = await Purchases.shared.checkTrialOrIntroDiscountEligibility(packages: packages)
            var map: [String: Bool] = [:]
            for (pkg, e) in result { map[pkg.storeProduct.productIdentifier] = (e.status == .eligible) }
            eligibility = map
        }
        .fullScreenCover(isPresented: $showRetention) {
            RetentionOfferHardView(
                onAccepted: { info in showRetention = false; onPurchaseSuccess(info) },
                onDeclined: {
                    AnalyticsManager.shared.trackPostHog("retention_offer_declined", properties: ["variant": "hard_2026_10_31"])
                    showRetention = false
                    onDismiss()
                }
            )
        }
    }

    private func feature(_ text: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "checkmark.circle.fill").foregroundStyle(AppTheme.Colors.accent).frame(width: 24)
            Text(text).font(.system(size: 14, weight: .medium)).foregroundStyle(AppTheme.Colors.label)
        }
    }

    private func card(_ p: Package) -> some View {
        let isSel = selected?.identifier == p.identifier
        let tr = trial(p)
        return Button { selected = p } label: {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(T.headline(p.storeProduct))
                        .font(.system(size: 18, weight: .bold)).foregroundStyle(AppTheme.Colors.label)
                    if p.packageType == .annual, let pm = p.storeProduct.localizedPricePerMonth {
                        Text(String(format: T.L("hp_per_month", "≈ %@ / month"), pm))
                            .font(.system(size: 13)).foregroundStyle(.secondary)
                    }
                    if let tr {
                        Text(String(format: T.L("hp_trial_badge", "%@ free trial"),
                                    "\(tr.subscriptionPeriod.value) \(T.periodText(SubscriptionPeriod(value: 1, unit: tr.subscriptionPeriod.unit)))"))
                            .font(.system(size: 13, weight: .medium)).foregroundStyle(AppTheme.Colors.accent)
                    }
                }
                Spacer()
                Image(systemName: isSel ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 24)).foregroundStyle(isSel ? AppTheme.Colors.accent : .secondary)
            }
            .padding(16)
            .background(isSel ? AppTheme.Colors.accent.opacity(0.1) : AppTheme.Colors.buttonUnselected)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(isSel ? AppTheme.Colors.accent : .clear, lineWidth: 2))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("paywall-plan-\(p.packageType.rawValue)")
    }

    private var cta: some View {
        VStack(spacing: 8) {
            if let errorMessage { Text(errorMessage).font(.caption).foregroundStyle(.red).padding(.horizontal, 24) }
            if let p = selected {
                // Billed amount is the most prominent element next to the button (3.1.2).
                Text(T.headline(p.storeProduct)).font(.system(size: 20, weight: .bold)).foregroundStyle(AppTheme.Colors.label)
            }
            Button { purchase() } label: {
                Group {
                    if isPurchasing { ProgressView().tint(.white) }
                    else { Text(selected.flatMap { trial($0) } != nil ? T.L("hp_cta_trial", "Start free trial") : T.L("hp_cta", "Continue")) }
                }
                .font(.system(size: 17, weight: .semibold)).foregroundStyle(.white)
                .frame(maxWidth: .infinity).frame(height: 54)
                .background(AppTheme.Colors.accent).clipShape(RoundedRectangle(cornerRadius: 27))
            }
            .disabled(selected == nil || isPurchasing)
            .accessibilityIdentifier("paywall-plan-cta")
            .padding(.horizontal, 24)
            if let p = selected {
                Text(T.disclosure(p.storeProduct, trial: trial(p)))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center).padding(.horizontal, 24)
                    .accessibilityIdentifier("paywall-terms")
            }
            footer
        }
        .padding(.bottom, 24)
    }

    private var footer: some View {
        HStack(spacing: 14) {
            Button(String(localized: "paywall_plan_restore")) { restore() }.accessibilityIdentifier("paywall-restore")
            Text("·")
            Link(String(localized: "paywall_plan_terms"), destination: AppConfig.termsURL)
            Text("·")
            Link(String(localized: "paywall_plan_privacy"), destination: AppConfig.privacyURL)
        }
        .font(.system(size: 12, weight: .medium)).foregroundStyle(.secondary)
    }

    private func purchase() {
        guard let p = selected else { return }
        isPurchasing = true; errorMessage = nil
        Task { @MainActor in
            defer { isPurchasing = false }
            do {
                let r = try await Purchases.shared.purchase(package: p)
                if !r.userCancelled {
                    AnalyticsManager.shared.track(.onboardingPaywallPurchased)
                    onPurchaseSuccess(r.customerInfo)
                }
            } catch let e as RevenueCat.ErrorCode where e == .purchaseCancelledError {
            } catch { errorMessage = error.localizedDescription }
        }
    }

    private func restore() {
        isPurchasing = true; errorMessage = nil
        Task { @MainActor in
            defer { isPurchasing = false }
            do {
                let info = try await Purchases.shared.restorePurchases()
                if info.entitlements[AppConfig.revenueCatEntitlementId]?.isActive == true { onPurchaseSuccess(info) }
                else { errorMessage = T.L("hp_restore_none", "No active subscription found.") }
            } catch { errorMessage = error.localizedDescription }
        }
    }
}

/// Single retention offer shown once when the user closes the hard paywall.
/// Product comes from RevenueCat offering `anicca_retention` (annual package → ai.anicca.app.ios.yearly.retention).
struct RetentionOfferHardView: View {
    let onAccepted: (CustomerInfo) -> Void
    let onDeclined: () -> Void
    @State private var pkg: Package?
    @State private var isPurchasing = false
    @State private var errorMessage: String?
    @State private var loadFailed = false
    private typealias T = PaywallTerms

    var body: some View {
        VStack(spacing: 18) {
            HStack { Spacer()
                Button(action: onDeclined) {
                    Image(systemName: "xmark").font(.system(size: 17, weight: .semibold)).foregroundStyle(.secondary)
                        .frame(width: 44, height: 44)
                }.accessibilityIdentifier("retention-close")
            }
            Text(String(localized: "retention_title")).font(.system(size: 28, weight: .bold))
                .multilineTextAlignment(.center).foregroundStyle(AppTheme.Colors.label)
            Text(String(localized: "retention_subtitle")).font(.system(size: 16)).foregroundStyle(.secondary)
                .multilineTextAlignment(.center).padding(.horizontal, 24)
            if let pkg {
                Text(T.headline(pkg.storeProduct)).font(.system(size: 34, weight: .heavy)).foregroundStyle(AppTheme.Colors.label)
                Spacer()
                Button { accept(pkg) } label: {
                    Group { if isPurchasing { ProgressView().tint(.white) } else { Text(String(localized: "retention_cta_accept")) } }
                        .font(.system(size: 18, weight: .semibold)).foregroundStyle(.white)
                        .frame(maxWidth: .infinity, minHeight: 54).background(AppTheme.Colors.label).clipShape(RoundedRectangle(cornerRadius: 27))
                }
                .disabled(isPurchasing).accessibilityIdentifier("retention-accept").padding(.horizontal, 24)
                Text(T.disclosure(pkg.storeProduct, trial: nil)).font(.system(size: 11)).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center).padding(.horizontal, 24)
            } else {
                if loadFailed { Text(String(localized: "paywall_b_load_failed")).font(.system(size: 14)).foregroundStyle(.secondary) }
                else { ProgressView() }
                Spacer()
            }
            if let errorMessage { Text(errorMessage).font(.caption).foregroundStyle(.red) }
            Button(T.L("hp_retention_decline", "No thanks")) { onDeclined() }
                .font(.system(size: 14, weight: .medium)).foregroundStyle(.secondary).accessibilityIdentifier("retention-decline")
            HStack(spacing: 14) {
                Link(String(localized: "paywall_plan_terms"), destination: AppConfig.termsURL)
                Text("·")
                Link(String(localized: "paywall_plan_privacy"), destination: AppConfig.privacyURL)
            }.font(.system(size: 12)).foregroundStyle(.secondary).padding(.bottom, 24)
        }
        .background(AppBackground())
        .task {
            AnalyticsManager.shared.trackPostHog("retention_offer_viewed", properties: ["variant": "hard_2026_10_31"])
            do {
                let o = try await Purchases.shared.offerings()
                if let p = o.offering(identifier: "anicca_retention")?.annual { pkg = p } else { loadFailed = true }
            } catch { loadFailed = true }
        }
    }

    private func accept(_ p: Package) {
        isPurchasing = true; errorMessage = nil
        Task { @MainActor in
            defer { isPurchasing = false }
            do {
                let r = try await Purchases.shared.purchase(package: p)
                if !r.userCancelled {
                    AnalyticsManager.shared.track(.onboardingPaywallPurchased)
                    onAccepted(r.customerInfo)
                }
            } catch let e as RevenueCat.ErrorCode where e == .purchaseCancelledError {
            } catch { errorMessage = error.localizedDescription }
        }
    }
}
