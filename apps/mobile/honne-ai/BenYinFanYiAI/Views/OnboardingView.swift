import SwiftUI

nonisolated enum OnboardingRelationship: String, CaseIterable, Sendable {
    case partner = "恋人・パートナー"
    case friend = "友人"
    case coworker = "職場の人"
    case family = "家族"

    var icon: String {
        switch self {
        case .partner: "heart.fill"
        case .friend: "person.2.fill"
        case .coworker: "building.2.fill"
        case .family: "house.fill"
        }
    }

    var color: Color {
        switch self {
        case .partner: .pink
        case .friend: .blue
        case .coworker: .orange
        case .family: .green
        }
    }
}

nonisolated enum OnboardingSituation: String, CaseIterable, Sendable {
    case coldReply = "LINEの返信が冷たい"
    case attitudeChange = "急に態度が変わった"
    case readIgnore = "既読スルーされる"
    case noHonesty = "本音を言ってくれない"
    case unknown = "何を考えてるかわからない"

    var icon: String {
        switch self {
        case .coldReply: "message.fill"
        case .attitudeChange: "arrow.triangle.2.circlepath"
        case .readIgnore: "eye.slash.fill"
        case .noHonesty: "lock.fill"
        case .unknown: "questionmark.circle.fill"
        }
    }
}

nonisolated enum OnboardingGoal: String, CaseIterable, Sendable {
    case trueFeelings = "相手の本当の気持ち"
    case bestReply = "ベストな返し方"
    case improveRelation = "関係を改善するヒント"

    var icon: String {
        switch self {
        case .trueFeelings: "heart.text.clipboard.fill"
        case .bestReply: "text.bubble.fill"
        case .improveRelation: "arrow.up.heart.fill"
        }
    }

    var color: Color {
        switch self {
        case .trueFeelings: .purple
        case .bestReply: .blue
        case .improveRelation: .green
        }
    }
}

struct OnboardingView: View {
    @State private var currentStep: Int = 0
    @State private var selectedRelationship: OnboardingRelationship?
    @State private var selectedSituations: Set<OnboardingSituation> = []
    @State private var selectedGoal: OnboardingGoal?
    @State private var showPaywall = false
    @State private var analysisProgress: Double = 0
    @State private var analysisPhase: Int = 0
    @State private var analysisComplete = false
    @State private var appeared = false

    let onComplete: () -> Void

    private let totalSteps = 8

    var body: some View {
        ZStack {
            Color(.systemBackground)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                if currentStep > 0 && currentStep < 7 {
                    progressBar
                        .padding(.top, 8)
                        .padding(.horizontal, 24)
                }

                Group {
                    switch currentStep {
                    case 0: welcomeScreen
                    case 1: relationshipScreen
                    case 2: situationScreen
                    case 3: goalScreen
                    case 4: analysisScreen
                    case 5: resultScreen
                    case 6: demoScreen
                    default: EmptyView()
                    }
                }
                .transition(.asymmetric(
                    insertion: .move(edge: .trailing).combined(with: .opacity),
                    removal: .move(edge: .leading).combined(with: .opacity)
                ))
            }
        }
        .animation(.spring(response: 0.45, dampingFraction: 0.85), value: currentStep)
        .sheet(isPresented: $showPaywall, onDismiss: {
            onComplete()
        }) {
            PaywallView()
        }
        .onAppear {
            withAnimation(.easeOut(duration: 0.6)) { appeared = true }
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Progress Bar

    private var progressBar: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color(.systemGray5))
                    .frame(height: 4)

                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [.purple, .indigo],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .frame(width: geo.size.width * CGFloat(currentStep) / CGFloat(totalSteps - 1), height: 4)
                    .animation(.spring(response: 0.4), value: currentStep)
            }
        }
        .frame(height: 4)
    }

    // MARK: - ① Welcome

    private var welcomeScreen: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 24) {
                ZStack {
                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [.purple.opacity(0.3), .indigo.opacity(0.2)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 120, height: 120)

                    Image(systemName: "brain.head.profile.fill")
                        .font(.system(size: 56))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [.purple, .indigo],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .symbolEffect(.pulse, options: .repeating)
                }
                .opacity(appeared ? 1 : 0)
                .scaleEffect(appeared ? 1 : 0.8)

                VStack(spacing: 12) {
                    Text("本音翻訳AI")
                        .font(.largeTitle.bold())

                    Text("相手の隠された本音を\nAIが読み解きます")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }
                .opacity(appeared ? 1 : 0)
                .offset(y: appeared ? 0 : 20)
            }

            Spacer()

            VStack(spacing: 20) {
                HStack(spacing: 4) {
                    ForEach(0..<5, id: \.self) { _ in
                        Image(systemName: "star.fill")
                            .font(.caption)
                            .foregroundStyle(.yellow)
                    }
                    Text("4.8")
                        .font(.subheadline.bold())
                        .foregroundStyle(.primary)
                }

                Text("50,000人以上が本音を見抜いています")
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                Button {
                    goToNext()
                } label: {
                    Text("はじめる")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                }
                .buttonStyle(.borderedProminent)
                .tint(.purple)
                .clipShape(.rect(cornerRadius: 14))
                .padding(.horizontal, 24)
            }
            .opacity(appeared ? 1 : 0)
            .offset(y: appeared ? 0 : 30)
            .padding(.bottom, 32)
        }
    }

    // MARK: - ② Relationship

    private var relationshipScreen: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 32) {
                VStack(spacing: 12) {
                    Text("一番気になる相手は？")
                        .font(.title3.bold())
                    Text("あなたの悩みに合わせて\n最適化します")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding(.horizontal, 24)

                VStack(spacing: 12) {
                    ForEach(OnboardingRelationship.allCases, id: \.rawValue) { relationship in
                        SelectionCard(
                            icon: relationship.icon,
                            text: relationship.rawValue,
                            color: relationship.color,
                            isSelected: selectedRelationship == relationship
                        ) {
                            selectedRelationship = relationship
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                                goToNext()
                            }
                        }
                    }
                }
                .padding(.horizontal, 24)
            }

            Spacer()
            Spacer()
        }
    }

    // MARK: - ③ Situation

    private var situationScreen: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 32) {
                VStack(spacing: 12) {
                    Text("どんな時にモヤモヤする？")
                        .font(.title3.bold())
                    Text("複数選べます")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 24)

                VStack(spacing: 10) {
                    ForEach(OnboardingSituation.allCases, id: \.rawValue) { situation in
                        SelectionCard(
                            icon: situation.icon,
                            text: situation.rawValue,
                            color: .indigo,
                            isSelected: selectedSituations.contains(situation)
                        ) {
                            if selectedSituations.contains(situation) {
                                selectedSituations.remove(situation)
                            } else {
                                selectedSituations.insert(situation)
                            }
                        }
                    }
                }
                .padding(.horizontal, 24)
            }

            Spacer()

            Button {
                goToNext()
            } label: {
                Text("次へ")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
            }
            .buttonStyle(.borderedProminent)
            .tint(.purple)
            .clipShape(.rect(cornerRadius: 14))
            .padding(.horizontal, 24)
            .padding(.bottom, 32)
            .opacity(selectedSituations.isEmpty ? 0.5 : 1)
            .disabled(selectedSituations.isEmpty)
        }
    }

    // MARK: - ④ Goal

    private var goalScreen: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 32) {
                VStack(spacing: 12) {
                    Text("一番知りたいことは？")
                        .font(.title3.bold())
                    Text("優先的に分析結果に反映します")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding(.horizontal, 24)

                VStack(spacing: 12) {
                    ForEach(OnboardingGoal.allCases, id: \.rawValue) { goal in
                        SelectionCard(
                            icon: goal.icon,
                            text: goal.rawValue,
                            color: goal.color,
                            isSelected: selectedGoal == goal
                        ) {
                            selectedGoal = goal
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                                goToNext()
                            }
                        }
                    }
                }
                .padding(.horizontal, 24)
            }

            Spacer()
            Spacer()
        }
    }

    // MARK: - ⑤ Analysis Loading

    private var analysisScreen: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 40) {
                ZStack {
                    Circle()
                        .stroke(Color(.systemGray5), lineWidth: 6)
                        .frame(width: 120, height: 120)

                    Circle()
                        .trim(from: 0, to: analysisProgress)
                        .stroke(
                            LinearGradient(
                                colors: [.purple, .indigo],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            style: StrokeStyle(lineWidth: 6, lineCap: .round)
                        )
                        .frame(width: 120, height: 120)
                        .rotationEffect(.degrees(-90))

                    Image(systemName: analysisComplete ? "checkmark" : "brain.head.profile.fill")
                        .font(.system(size: 40))
                        .foregroundStyle(analysisComplete ? .green : .purple)
                        .contentTransition(.symbolEffect(.replace))
                        .symbolEffect(.pulse, options: .repeating, isActive: !analysisComplete)
                }

                VStack(spacing: 12) {
                    Text(analysisStatusText)
                        .font(.title3.bold())
                        .multilineTextAlignment(.center)
                        .contentTransition(.numericText())

                    if let relationship = selectedRelationship {
                        Text("\(relationship.rawValue)との関係を分析中")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Spacer()
        }
        .task {
            await runAnalysisAnimation()
        }
    }

    private var analysisStatusText: String {
        switch analysisPhase {
        case 0: "あなたの悩みを分析中…"
        case 1: "最適な機能を選定中…"
        case 2: "パーソナライズ中…"
        default: "準備完了！"
        }
    }

    private func runAnalysisAnimation() async {
        let phases = [0.3, 0.65, 0.9, 1.0]
        for (index, target) in phases.enumerated() {
            try? await Task.sleep(for: .milliseconds(900))
            withAnimation(.spring(response: 0.5)) {
                analysisPhase = index
                analysisProgress = target
            }
        }
        try? await Task.sleep(for: .milliseconds(400))
        withAnimation {
            analysisComplete = true
        }
        try? await Task.sleep(for: .milliseconds(600))
        goToNext()
    }

    // MARK: - ⑥ Personalized Result

    private var resultScreen: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 32) {
                VStack(spacing: 12) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 36))
                        .foregroundStyle(.yellow)
                        .symbolEffect(.bounce, value: currentStep)

                    Text("あなたにぴったりの\n分析が見つかりました")
                        .font(.title3.bold())
                        .multilineTextAlignment(.center)
                }

                VStack(spacing: 12) {
                    ForEach(Array(personalizedFeatures.enumerated()), id: \.offset) { index, feature in
                        ResultFeatureCard(
                            icon: feature.icon,
                            title: feature.title,
                            subtitle: feature.subtitle,
                            color: feature.color,
                            delay: Double(index) * 0.15
                        )
                    }
                }
                .padding(.horizontal, 24)
            }

            Spacer()

            Button {
                goToNext()
            } label: {
                Text("つづける")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
            }
            .buttonStyle(.borderedProminent)
            .tint(.purple)
            .clipShape(.rect(cornerRadius: 14))
            .padding(.horizontal, 24)
            .padding(.bottom, 32)
        }
    }

    private var personalizedFeatures: [(icon: String, title: String, subtitle: String, color: Color)] {
        let relationLabel = selectedRelationship?.rawValue ?? "相手"
        return [
            (
                icon: "brain.head.profile.fill",
                title: "\(relationLabel)の本音分析",
                subtitle: "メッセージから隠された感情を読み解きます",
                color: .purple
            ),
            (
                icon: "text.bubble.fill",
                title: "最適な返答の提案",
                subtitle: "関係を壊さないベストな返し方をAIが提案",
                color: .blue
            ),
            (
                icon: "heart.text.clipboard.fill",
                title: "心理レポート",
                subtitle: "怒り・不安・期待…相手の感情を深く分析",
                color: .orange
            ),
        ]
    }

    // MARK: - ⑦ Demo

    private var demoScreen: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 24) {
                Text("こんな風に本音がわかります")
                    .font(.title3.bold())
                    .padding(.horizontal, 24)

                VStack(spacing: 16) {
                    HStack {
                        Spacer()
                        VStack(alignment: .trailing, spacing: 4) {
                            Text("送信メッセージ")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text("今日忙しい？")
                                .font(.body)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                                .background(Color.purple.opacity(0.3))
                                .clipShape(.rect(cornerRadius: 18, style: .continuous))
                        }
                    }

                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("相手の返信")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text("うん、まあまあかな")
                                .font(.body)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                                .background(Color(.secondarySystemGroupedBackground))
                                .clipShape(.rect(cornerRadius: 18, style: .continuous))
                        }
                        Spacer()
                    }

                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 8) {
                            Image(systemName: "brain.head.profile.fill")
                                .foregroundStyle(.purple)
                            Text("AIの本音分析")
                                .font(.headline)
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            AnalysisRow(label: "本音", value: "誘ってほしいけど自分からは言いたくない", emoji: "💭")
                            AnalysisRow(label: "感情", value: "期待 80% ・ 照れ 15% ・ 不安 5%", emoji: "📊")
                            AnalysisRow(label: "返答例", value: "「じゃあ夜ご飯でも行かない？」", emoji: "💡")
                        }
                    }
                    .padding(16)
                    .background(
                        LinearGradient(
                            colors: [.purple.opacity(0.1), .indigo.opacity(0.05)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .clipShape(.rect(cornerRadius: 16))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .strokeBorder(Color.purple.opacity(0.2), lineWidth: 1)
                    )
                }
                .padding(.horizontal, 24)
            }

            Spacer()

            Button {
                showPaywall = true
            } label: {
                Text("あなた専用プランを始める")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
            }
            .buttonStyle(.borderedProminent)
            .tint(.purple)
            .clipShape(.rect(cornerRadius: 14))
            .padding(.horizontal, 24)
            .padding(.bottom, 32)
        }
    }

    // MARK: - Navigation

    private func goToNext() {
        withAnimation {
            currentStep += 1
        }
    }
}

// MARK: - Supporting Views

struct SelectionCard: View {
    let icon: String
    let text: String
    let color: Color
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: icon)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(isSelected ? .white : color)
                    .frame(width: 36, height: 36)
                    .background(isSelected ? color : color.opacity(0.15))
                    .clipShape(Circle())

                Text(text)
                    .font(.body.weight(.medium))
                    .foregroundStyle(.primary)

                Spacer()

                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(color)
                        .transition(.scale.combined(with: .opacity))
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(
                isSelected
                    ? color.opacity(0.1)
                    : Color(.secondarySystemGroupedBackground)
            )
            .clipShape(.rect(cornerRadius: 14))
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .strokeBorder(
                        isSelected ? color.opacity(0.4) : Color.clear,
                        lineWidth: 1.5
                    )
            )
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: isSelected)
        .animation(.spring(response: 0.3), value: isSelected)
    }
}

struct ResultFeatureCard: View {
    let icon: String
    let title: String
    let subtitle: String
    let color: Color
    let delay: Double

    @State private var appeared = false

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(color)
                .frame(width: 44, height: 44)
                .background(color.opacity(0.15))
                .clipShape(.rect(cornerRadius: 12))

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Spacer()
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(.rect(cornerRadius: 14))
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : 16)
        .onAppear {
            withAnimation(.spring(response: 0.5).delay(delay)) {
                appeared = true
            }
        }
    }
}

struct AnalysisRow: View {
    let label: String
    let value: String
    let emoji: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text(emoji)
                .font(.body)
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.subheadline)
            }
        }
    }
}
