import SwiftUI

struct SettingsView: View {
    @Environment(SubscriptionService.self) private var subscriptionService
    @State private var showPaywall = false

    private var privacyPolicyURL: URL {
        URL(string: "https://daisuke134.github.io/rork--ai/privacy-policy.html")!
    }
    private var termsURL: URL {
        URL(string: "\(Config.EXPO_PUBLIC_RORK_API_BASE_URL)/api/terms/ja") ?? URL(string: "https://apple.com")!
    }

    var body: some View {
        NavigationStack {
            List {
                subscriptionSection
                dataSection
                aboutSection
                legalSection
            }
            .listStyle(.insetGrouped)
            .navigationTitle("設定")
            .navigationBarTitleDisplayMode(.large)
            .sheet(isPresented: $showPaywall) {
                PaywallView()
            }
        }
    }

    private var subscriptionSection: some View {
        Section {
            if subscriptionService.isPremium {
                HStack(spacing: 12) {
                    Image(systemName: "crown.fill")
                        .font(.title3)
                        .foregroundStyle(.yellow)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("プレミアム会員")
                            .font(.headline)
                        Text("全ての機能が利用可能です")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 4)
            } else {
                Button {
                    showPaywall = true
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "crown.fill")
                            .font(.title3)
                            .foregroundStyle(.purple)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("プレミアムにアップグレード")
                                .font(.headline)
                            Text("無制限の翻訳と詳細分析")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }
                .padding(.vertical, 4)
            }

            Button {
                Task { await subscriptionService.restorePurchases() }
            } label: {
                Label("購入を復元", systemImage: "arrow.clockwise")
            }
        } header: {
            Text("サブスクリプション")
        }
    }

    private var dataSection: some View {
        Section {
            HStack(spacing: 12) {
                Image(systemName: "info.circle")
                    .foregroundStyle(.blue)
                VStack(alignment: .leading, spacing: 2) {
                    Text("データの取り扱い")
                        .font(.subheadline)
                    Text("入力されたメッセージはAI分析のためにOpenAI社のサーバーに送信されます。個人情報や機密情報の入力はお控えください。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 4)

            Button {
                UserDefaults.standard.set(false, forKey: "hasAcceptedDataConsent")
            } label: {
                Label("データ同意をリセット", systemImage: "arrow.counterclockwise")
            }
        } header: {
            Text("プライバシー")
        }
    }

    private var aboutSection: some View {
        Section {
            HStack {
                Text("バージョン")
                Spacer()
                Text("1.0.0")
                    .foregroundStyle(.secondary)
            }
        } header: {
            Text("アプリ情報")
        }
    }

    private var legalSection: some View {
        Section {
            Link(destination: termsURL) {
                Label("利用規約（EULA）", systemImage: "doc.text")
            }
            Link(destination: privacyPolicyURL) {
                Label("プライバシーポリシー", systemImage: "hand.raised")
            }
        } header: {
            Text("法的情報")
        }
    }
}
