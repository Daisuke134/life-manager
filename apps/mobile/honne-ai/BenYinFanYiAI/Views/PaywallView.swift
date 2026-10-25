import SwiftUI
import RevenueCat

struct PaywallView: View {
    @Environment(SubscriptionService.self) private var subscriptionService
    @Environment(\.dismiss) private var dismiss
    @State private var appeared = false
    @State private var selectedPackage: Package?
    @State private var trialEligibleProducts: Set<String> = []

    /// Hard paywall: no close button, no swipe-down; leaves only after purchase or restore.
    var isHard: Bool = false
    /// Called once premium is active. Defaults to dismissing the sheet.
    var onUnlocked: (() -> Void)? = nil

    private var privacyPolicyURL: URL {
        URL(string: "https://daisuke134.github.io/rork--ai/privacy-policy.html")!
    }
    private var termsURL: URL {
        // Apple's standard EULA (accepted for auto-renewable subscriptions, guideline 3.1.2).
        URL(string: "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/")!
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 28) {
                    premiumHeader
                    featureList
                    packagesSection
                    restoreButton
                    termsSection
                }
                .padding(.horizontal)
                .padding(.top, 8)
                .padding(.bottom, 32)
            }
            .navigationTitle("プレミアム")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if !isHard {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("閉じる") { dismiss() }
                    }
                }
            }
            .task {
                await subscriptionService.fetchOfferings()
                await loadPlans()
            }
            .onAppear {
                withAnimation(.spring(response: 0.6)) { appeared = true }
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(isHard ? .hidden : .visible)
        .interactiveDismissDisabled(isHard)
    }

    private var packages: [Package] {
        subscriptionService.offerings?.current?.availablePackages ?? []
    }

    private func loadPlans() async {
        let available = packages
        if selectedPackage == nil {
            selectedPackage = available.first { $0.packageType == .annual } ?? available.first
        }
        guard !available.isEmpty else { return }
        let eligibility = await Purchases.shared.checkTrialOrIntroDiscountEligibility(packages: available)
        trialEligibleProducts = Set(eligibility.compactMap { package, status in
            status.status == .eligible ? package.storeProduct.productIdentifier : nil
        })
    }

    // Free-trial length in the store's own unit ("3日間", "1か月間"), only when the product has one and this user is eligible.
    private func trialPeriod(_ package: Package?) -> String? {
        guard let product = package?.storeProduct,
              trialEligibleProducts.contains(product.productIdentifier),
              let intro = product.introductoryDiscount,
              intro.paymentMode == .freeTrial else { return nil }
        let period = intro.subscriptionPeriod
        switch period.unit {
        case .day: return "\(period.value)日間"
        case .week: return "\(period.value)週間"
        case .month: return "\(period.value)か月間"
        case .year: return "\(period.value)年間"
        @unknown default: return nil
        }
    }

    private func annualSavingsPercent(_ annual: Package) -> Int? {
        let base = packages.first { $0.packageType == .weekly } ?? packages.first { $0.packageType == .monthly }
        guard let base else { return nil }
        let periodsPerYear: Decimal = base.packageType == .weekly ? 52 : 12
        return PlanPricing.annualSavingsPercent(
            annual: annual.storeProduct.price,
            periodPrice: base.storeProduct.price,
            periodsPerYear: periodsPerYear
        )
    }

    private func unlock() {
        if let onUnlocked { onUnlocked() } else { dismiss() }
    }

    private var premiumHeader: some View {
        VStack(spacing: 16) {
            ZStack {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [.purple, .indigo],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 80, height: 80)

                Image(systemName: "crown.fill")
                    .font(.system(size: 36))
                    .foregroundStyle(.white)
                    .symbolEffect(.bounce, value: appeared)
            }

            Text("本音翻訳AI プレミアム")
                .font(.title2.bold())

            Text("無制限の翻訳で人間関係をもっと深く理解")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : 20)
    }

    private var featureList: some View {
        VStack(spacing: 14) {
            FeatureRow(icon: "infinity", color: .purple, text: "翻訳回数が無制限")
            FeatureRow(icon: "bolt.fill", color: .orange, text: "優先的な高速分析")
            FeatureRow(icon: "clock.arrow.circlepath", color: .blue, text: "全ての翻訳履歴にアクセス")
            FeatureRow(icon: "sparkles", color: .indigo, text: "より詳細な心理分析")
        }
        .padding(16)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(.rect(cornerRadius: 16))
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : 20)
        .animation(.spring(response: 0.5).delay(0.1), value: appeared)
    }

    private var packagesSection: some View {
        VStack(spacing: 12) {
            if subscriptionService.isLoading {
                ProgressView()
                    .padding(40)
            } else if !packages.isEmpty {
                ForEach(packages, id: \.identifier) { package in
                    PackageCard(
                        package: package,
                        isSelected: selectedPackage?.identifier == package.identifier,
                        savingsPercent: package.packageType == .annual ? annualSavingsPercent(package) : nil,
                        trialPeriod: trialPeriod(package)
                    ) {
                        selectedPackage = package
                    }
                }

                Button {
                    guard let package = selectedPackage else { return }
                    Task {
                        let success = await subscriptionService.purchase(package: package)
                        if success { unlock() }
                    }
                } label: {
                    Text(trialPeriod(selectedPackage).map { "\($0)無料で始める" } ?? "続ける")
                        .font(.headline)
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .frame(height: 54)
                        .background(Color.accentColor)
                        .clipShape(.rect(cornerRadius: 14))
                }
                .disabled(selectedPackage == nil || subscriptionService.isLoading)
                .accessibilityIdentifier("paywall_cta")
            } else {
                // No plans (load error or empty offering): always offer a retry so the hard paywall never dead-ends.
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.title2)
                        .foregroundStyle(.orange)
                    Text("プランの読み込みに失敗しました")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Button("再試行") {
                        Task {
                            await subscriptionService.fetchOfferings()
                            await loadPlans()
                        }
                    }
                    .font(.subheadline.weight(.semibold))
                }
                .padding(24)
            }

            if let error = subscriptionService.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : 20)
        .animation(.spring(response: 0.5).delay(0.2), value: appeared)
    }

    private var restoreButton: some View {
        Button {
            Task {
                await subscriptionService.restorePurchases()
                if subscriptionService.isPremium { unlock() }
            }
        } label: {
            Text("購入を復元")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private var termsSection: some View {
        VStack(spacing: 8) {
            Text("サブスクリプションは自動更新されます。次の更新日の24時間前までにキャンセルしない限り、自動的に更新されます。購入の確認後、お支払いはApple IDアカウントに請求されます。")
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                Link("利用規約", destination: termsURL)
                    .font(.caption2)

                Text("・")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)

                Link("プライバシーポリシー", destination: privacyPolicyURL)
                    .font(.caption2)
            }
        }
    }
}

struct FeatureRow: View {
    let icon: String
    let color: Color
    let text: String

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.body.weight(.semibold))
                .foregroundStyle(color)
                .frame(width: 32)

            Text(text)
                .font(.body)

            Spacer()
        }
    }
}

struct PackageCard: View {
    let package: Package
    let isSelected: Bool
    let savingsPercent: Int?
    let trialPeriod: String?
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(packageTitle)
                            .font(.headline)

                        if isAnnual {
                            Text(savingsPercent.map { "\($0)%お得" } ?? "おすすめ")
                                .font(.caption2.weight(.bold))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color.green)
                                .foregroundStyle(.white)
                                .clipShape(Capsule())
                        }
                    }

                    if !packageDescription.isEmpty {
                        Text(packageDescription)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 2) {
                    Text(package.storeProduct.localizedPriceString)
                        .font(.title3.bold())
                    Text(pricePeriod)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(16)
            .background(
                isSelected
                    ? Color.accentColor.opacity(0.08)
                    : Color(.secondarySystemGroupedBackground)
            )
            .clipShape(.rect(cornerRadius: 14))
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .strokeBorder(
                        isSelected ? Color.accentColor : Color(.separator).opacity(0.3),
                        lineWidth: isSelected ? 2 : 1
                    )
            )
        }
        .buttonStyle(.plain)
    }

    private var isAnnual: Bool {
        package.packageType == .annual
    }

    private var packageTitle: String {
        switch package.packageType {
        case .weekly: return "週額プラン"
        case .monthly: return "月額プラン"
        case .annual: return "年額プラン"
        default: return package.storeProduct.localizedTitle
        }
    }

    private var packageDescription: String {
        let trial = trialPeriod.map { "\($0)無料、その後" } ?? ""
        switch package.packageType {
        case .weekly: return trial + "1週間ごとの自動更新・いつでもキャンセル可能"
        case .monthly: return trial + "1ヶ月ごとの自動更新・いつでもキャンセル可能"
        case .annual:
            let perWeek = package.storeProduct.localizedPricePerWeek.map { "・週あたり\($0)" } ?? ""
            return trial + "1年ごとの自動更新" + perWeek
        default: return trial
        }
    }

    private var pricePeriod: String {
        switch package.packageType {
        case .weekly: return "/週"
        case .monthly: return "/月"
        case .annual: return "/年"
        default: return ""
        }
    }
}

enum PlanPricing {
    // Annual vs a year of the shorter plan, as a whole percent; nil when annual is not cheaper.
    static func annualSavingsPercent(annual: Decimal, periodPrice: Decimal, periodsPerYear: Decimal) -> Int? {
        let yearOfPeriods = periodPrice * periodsPerYear
        guard yearOfPeriods > 0, annual < yearOfPeriods else { return nil }
        let percent = NSDecimalNumber(decimal: (1 - annual / yearOfPeriods) * 100).doubleValue
        let rounded = Int(percent.rounded())
        return rounded > 0 ? rounded : nil
    }
}
