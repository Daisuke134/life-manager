import SwiftUI
import RevenueCat

struct PaywallView: View {
    @Environment(SubscriptionService.self) private var subscriptionService
    @Environment(\.dismiss) private var dismiss
    @State private var appeared = false

    private var privacyPolicyURL: URL {
        URL(string: "https://daisuke134.github.io/rork--ai/privacy-policy.html")!
    }
    private var termsURL: URL {
        URL(string: "\(Config.EXPO_PUBLIC_RORK_API_BASE_URL)/api/terms/ja") ?? URL(string: "https://apple.com")!
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
                ToolbarItem(placement: .topBarTrailing) {
                    Button("閉じる") { dismiss() }
                }
            }
            .task {
                await subscriptionService.fetchOfferings()
            }
            .onAppear {
                withAnimation(.spring(response: 0.6)) { appeared = true }
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
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
            } else if let offerings = subscriptionService.offerings,
                      let current = offerings.current {
                ForEach(current.availablePackages, id: \.identifier) { package in
                    PackageCard(package: package) {
                        Task {
                            let success = await subscriptionService.purchase(package: package)
                            if success { dismiss() }
                        }
                    }
                }
            } else if subscriptionService.errorMessage != nil {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.title2)
                        .foregroundStyle(.orange)
                    Text("プランの読み込みに失敗しました")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Button("再試行") {
                        Task { await subscriptionService.fetchOfferings() }
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
            Task { await subscriptionService.restorePurchases() }
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
    let onPurchase: () -> Void

    var body: some View {
        Button(action: onPurchase) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(packageTitle)
                            .font(.headline)

                        if isAnnual {
                            Text("おすすめ")
                                .font(.caption2.weight(.bold))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color.green)
                                .foregroundStyle(.white)
                                .clipShape(Capsule())
                        }
                    }

                    Text(packageDescription)
                        .font(.caption)
                        .foregroundStyle(.secondary)
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
                isAnnual
                    ? Color.accentColor.opacity(0.08)
                    : Color(.secondarySystemGroupedBackground)
            )
            .clipShape(.rect(cornerRadius: 14))
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .strokeBorder(
                        isAnnual ? Color.accentColor.opacity(0.3) : Color(.separator).opacity(0.3),
                        lineWidth: 1
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
        case .monthly: return "月額プラン"
        case .annual: return "年額プラン"
        default: return package.storeProduct.localizedTitle
        }
    }

    private var packageDescription: String {
        switch package.packageType {
        case .monthly: return "1ヶ月ごとの自動更新・いつでもキャンセル可能"
        case .annual: return "1年ごとの自動更新・月額換算で50%お得"
        default: return ""
        }
    }

    private var pricePeriod: String {
        switch package.packageType {
        case .monthly: return "/月"
        case .annual: return "/年"
        default: return ""
        }
    }
}
