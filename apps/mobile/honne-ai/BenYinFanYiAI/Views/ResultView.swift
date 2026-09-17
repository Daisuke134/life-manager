import SwiftUI

struct ResultView: View {
    let result: TranslationResult
    @Environment(\.dismiss) private var dismiss
    @State private var appeared = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    emotionHeader
                    originalMessageCard
                    honneCard
                    psychologyCard
                    responseCard
                }
                .padding(.horizontal)
                .padding(.top, 8)
                .padding(.bottom, 32)
            }
            .navigationTitle("分析結果")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("閉じる") { dismiss() }
                }
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .onAppear {
            withAnimation(.spring(response: 0.6, dampingFraction: 0.8)) {
                appeared = true
            }
        }
    }

    private var emotionHeader: some View {
        VStack(spacing: 12) {
            HStack(spacing: 4) {
                ForEach(1...5, id: \.self) { level in
                    Image(systemName: level <= result.emotionLevel ? "flame.fill" : "flame")
                        .font(.title2)
                        .foregroundStyle(level <= result.emotionLevel ? emotionColor : .gray.opacity(0.3))
                        .symbolEffect(.bounce, value: appeared && level <= result.emotionLevel)
                }
            }

            Text(emotionLabel)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)

            HStack(spacing: 6) {
                Image(systemName: result.relationship.icon)
                    .font(.caption)
                Text(result.relationship.displayName)
                    .font(.caption)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.thinMaterial)
            .clipShape(Capsule())
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : 20)
    }

    private var originalMessageCard: some View {
        ResultCard(
            icon: "text.bubble.fill",
            iconColor: .blue,
            title: "元のメッセージ",
            content: result.originalText,
            delay: 0.1,
            appeared: appeared
        )
    }

    private var honneCard: some View {
        ResultCard(
            icon: "brain.head.profile.fill",
            iconColor: .purple,
            title: "相手の本音",
            content: result.honne,
            delay: 0.2,
            appeared: appeared,
            highlighted: true
        )
    }

    private var psychologyCard: some View {
        ResultCard(
            icon: "heart.text.clipboard.fill",
            iconColor: .orange,
            title: "心理状態",
            content: result.psychologicalState,
            delay: 0.3,
            appeared: appeared
        )
    }

    private var responseCard: some View {
        ResultCard(
            icon: "bubble.left.and.text.bubble.right.fill",
            iconColor: .green,
            title: "おすすめの返答",
            content: result.suggestedResponse,
            delay: 0.4,
            appeared: appeared
        )
    }

    private var emotionColor: Color {
        switch result.emotionLevel {
        case 1: return .green
        case 2: return .yellow
        case 3: return .orange
        case 4: return .red
        default: return .purple
        }
    }

    private var emotionLabel: String {
        switch result.emotionLevel {
        case 1: return "穏やか"
        case 2: return "やや感情的"
        case 3: return "感情的"
        case 4: return "かなり感情的"
        default: return "非常に感情的"
        }
    }
}

struct ResultCard: View {
    let icon: String
    let iconColor: Color
    let title: String
    let content: String
    let delay: Double
    let appeared: Bool
    var highlighted: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.subheadline)
                    .foregroundStyle(iconColor)
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            Text(content)
                .font(.body)
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(
            highlighted
                ? AnyShapeStyle(iconColor.opacity(0.08))
                : AnyShapeStyle(Color(.secondarySystemGroupedBackground))
        )
        .clipShape(.rect(cornerRadius: 16))
        .overlay(
            highlighted
                ? RoundedRectangle(cornerRadius: 16).strokeBorder(iconColor.opacity(0.2), lineWidth: 1)
                : nil
        )
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : 20)
        .animation(.spring(response: 0.5, dampingFraction: 0.8).delay(delay), value: appeared)
    }
}
