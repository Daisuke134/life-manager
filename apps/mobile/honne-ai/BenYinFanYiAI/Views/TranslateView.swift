import SwiftUI

struct TranslateView: View {
    @Environment(AIService.self) private var aiService
    @Environment(SubscriptionService.self) private var subscriptionService
    @Environment(HistoryService.self) private var historyService
    @State private var inputText = ""
    @State private var selectedRelationship: RelationshipType = .couple
    @State private var result: TranslationResult?
    @State private var showResult = false
    @State private var showPaywall = false
    @State private var animateGradient = false
    @State private var showError = false
    @State private var showDataConsentAlert = false
    @FocusState private var isInputFocused: Bool

    private let hasAcceptedDataConsentKey = "hasAcceptedDataConsent"

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    headerSection
                    relationshipPicker
                    inputSection
                    analyzeButton
                    usageIndicator
                }
                .padding(.horizontal)
                .padding(.top, 8)
                .padding(.bottom, 32)
            }
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("本音翻訳")
            .navigationBarTitleDisplayMode(.large)
            .sheet(isPresented: $showResult) {
                if let result {
                    ResultView(result: result)
                }
            }
            .sheet(isPresented: $showPaywall) {
                PaywallView()
            }
            .alert("エラー", isPresented: $showError) {
                Button("OK") { aiService.errorMessage = nil }
            } message: {
                Text(aiService.errorMessage ?? "不明なエラーが発生しました")
            }
            .alert("データの取り扱いについて", isPresented: $showDataConsentAlert) {
                Button("同意して利用する") {
                    UserDefaults.standard.set(true, forKey: hasAcceptedDataConsentKey)
                    Task { await performAnalysis() }
                }
                Button("キャンセル", role: .cancel) {}
            } message: {
                Text("入力されたメッセージはAI分析のためにOpenAI社のサーバーに送信されます。個人情報や機密情報の入力はお控えください。詳細はプライバシーポリシーをご確認ください。")
            }
        }
    }

    private var headerSection: some View {
        VStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 20)
                    .fill(
                        MeshGradient(
                            width: 3, height: 3,
                            points: [
                                [0, 0], [0.5, 0], [1, 0],
                                [0, 0.5], [0.5, 0.5], [1, 0.5],
                                [0, 1], [0.5, 1], [1, 1]
                            ],
                            colors: [
                                .indigo.opacity(0.3), .purple.opacity(0.4), .blue.opacity(0.3),
                                .purple.opacity(0.3), .indigo.opacity(0.5), .purple.opacity(0.3),
                                .blue.opacity(0.3), .indigo.opacity(0.4), .purple.opacity(0.3)
                            ]
                        )
                    )
                    .frame(height: 140)

                VStack(spacing: 8) {
                    Image(systemName: "brain.head.profile.fill")
                        .font(.system(size: 36))
                        .foregroundStyle(.white)
                        .symbolEffect(.pulse, options: .repeating)

                    Text("相手の本音を読み解く")
                        .font(.headline)
                        .foregroundStyle(.white)

                    Text("LINEや会話文を入力してAIが分析します")
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.8))
                }
            }
        }
    }

    private var relationshipPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("関係性を選択")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)

            ScrollView(.horizontal) {
                HStack(spacing: 10) {
                    ForEach(RelationshipType.allCases, id: \.self) { type in
                        Button {
                            withAnimation(.snappy) {
                                selectedRelationship = type
                            }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: type.icon)
                                    .font(.subheadline)
                                Text(type.displayName)
                                    .font(.subheadline)
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 10)
                            .background(
                                selectedRelationship == type
                                    ? Color.accentColor
                                    : Color(.tertiarySystemBackground)
                            )
                            .foregroundStyle(
                                selectedRelationship == type ? .white : .primary
                            )
                            .clipShape(Capsule())
                        }
                        .sensoryFeedback(.selection, trigger: selectedRelationship)
                    }
                }
            }
            .contentMargins(.horizontal, 0)
            .scrollIndicators(.hidden)
        }
    }

    private var inputSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("メッセージを入力")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                if !inputText.isEmpty {
                    Button("クリア") {
                        withAnimation { inputText = "" }
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
            }

            ZStack(alignment: .topLeading) {
                TextEditor(text: $inputText)
                    .focused($isInputFocused)
                    .frame(minHeight: 150, maxHeight: 250)
                    .scrollContentBackground(.hidden)
                    .padding(12)
                    .background(Color(.secondarySystemGroupedBackground))
                    .clipShape(.rect(cornerRadius: 16))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .strokeBorder(
                                isInputFocused ? Color.accentColor.opacity(0.5) : Color(.separator).opacity(0.3),
                                lineWidth: 1
                            )
                    )

                if inputText.isEmpty {
                    Text("例：「別に怒ってないよ」「好きにすれば？」")
                        .font(.body)
                        .foregroundStyle(Color(.placeholderText))
                        .padding(.horizontal, 16)
                        .padding(.vertical, 20)
                        .allowsHitTesting(false)
                }
            }
        }
    }

    private var analyzeButton: some View {
        Button {
            Task { await analyze() }
        } label: {
            HStack(spacing: 10) {
                if aiService.isAnalyzing {
                    ProgressView()
                        .tint(.white)
                } else {
                    Image(systemName: "sparkles")
                        .font(.body.weight(.semibold))
                }
                Text(aiService.isAnalyzing ? "分析中..." : "本音を翻訳する")
                    .font(.body.weight(.semibold))
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
        }
        .buttonStyle(.borderedProminent)
        .clipShape(.rect(cornerRadius: 14))
        .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || aiService.isAnalyzing)
        .sensoryFeedback(.impact(weight: .medium), trigger: showResult)
    }

    private var usageIndicator: some View {
        Group {
            if !subscriptionService.isPremium {
                HStack(spacing: 8) {
                    Image(systemName: "info.circle")
                        .font(.caption)
                    Text("今日の無料翻訳: 残り\(subscriptionService.freeUsesRemaining)回")
                        .font(.caption)
                    Spacer()
                    Button("プレミアムへ") {
                        showPaywall = true
                    }
                    .font(.caption.weight(.semibold))
                }
                .foregroundStyle(.secondary)
                .padding(12)
                .background(Color(.tertiarySystemBackground))
                .clipShape(.rect(cornerRadius: 12))
            }
        }
    }

    private func analyze() async {
        guard !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }

        if !subscriptionService.canUseTranslation() {
            showPaywall = true
            return
        }

        let hasConsented = UserDefaults.standard.bool(forKey: hasAcceptedDataConsentKey)
        if !hasConsented {
            showDataConsentAlert = true
            return
        }

        await performAnalysis()
    }

    private func performAnalysis() async {
        isInputFocused = false

        if let translationResult = await aiService.analyzeMessage(inputText, relationship: selectedRelationship) {
            result = translationResult
            subscriptionService.consumeFreeUse()
            historyService.addResult(translationResult)
            showResult = true
        } else if aiService.errorMessage != nil {
            showError = true
        }
    }
}
