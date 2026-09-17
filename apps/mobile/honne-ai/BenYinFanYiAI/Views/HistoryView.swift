import SwiftUI

struct HistoryView: View {
    @Environment(HistoryService.self) private var historyService
    @State private var selectedResult: TranslationResult?
    @State private var showClearAlert = false

    var body: some View {
        NavigationStack {
            Group {
                if historyService.results.isEmpty {
                    ContentUnavailableView(
                        "履歴がありません",
                        systemImage: "clock.arrow.circlepath",
                        description: Text("翻訳結果がここに表示されます")
                    )
                } else {
                    List {
                        ForEach(historyService.results) { result in
                            Button {
                                selectedResult = result
                            } label: {
                                HistoryRow(result: result)
                            }
                            .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                        }
                        .onDelete(perform: historyService.removeResult)
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("翻訳履歴")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                if !historyService.results.isEmpty {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("全削除", role: .destructive) {
                            showClearAlert = true
                        }
                        .foregroundStyle(.red)
                    }
                }
            }
            .alert("履歴を全て削除しますか？", isPresented: $showClearAlert) {
                Button("削除", role: .destructive) {
                    withAnimation { historyService.clearAll() }
                }
                Button("キャンセル", role: .cancel) { }
            } message: {
                Text("この操作は取り消せません")
            }
            .sheet(item: $selectedResult) { result in
                ResultView(result: result)
            }
        }
    }
}

struct HistoryRow: View {
    let result: TranslationResult

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                HStack(spacing: 4) {
                    Image(systemName: result.relationship.icon)
                        .font(.caption2)
                    Text(result.relationship.displayName)
                        .font(.caption)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.accentColor.opacity(0.1))
                .foregroundStyle(Color.accentColor)
                .clipShape(Capsule())

                Spacer()

                HStack(spacing: 2) {
                    ForEach(1...5, id: \.self) { level in
                        Circle()
                            .fill(level <= result.emotionLevel ? emotionColor(for: result.emotionLevel) : Color.gray.opacity(0.2))
                            .frame(width: 6, height: 6)
                    }
                }

                Text(result.timestamp, format: .dateTime.month().day().hour().minute())
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            Text(result.originalText)
                .font(.body)
                .lineLimit(2)
                .foregroundStyle(.primary)

            Text(result.honne)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(.vertical, 4)
    }

    private func emotionColor(for level: Int) -> Color {
        switch level {
        case 1: return .green
        case 2: return .yellow
        case 3: return .orange
        case 4: return .red
        default: return .purple
        }
    }
}
