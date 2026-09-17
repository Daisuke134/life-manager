#if DEBUG
import SwiftUI

/// デバッグ用: LLMNudgeCache の全 Nudge を時系列テーブルで表示
struct LLMNudgeDebugView: View {
    @State private var nudges: [LLMGeneratedNudge] = []
    @State private var selectedNudge: LLMGeneratedNudge?

    var body: some View {
        List {
            if nudges.isEmpty {
                Text("Nudge がキャッシュされていません")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 40)
                    .accessibilityIdentifier("debug-nudge-list-empty")
            } else {
                Section("Cached Nudges (\(nudges.count))") {
                    ForEach(nudges, id: \.id) { nudge in
                        Button {
                            selectedNudge = nudge
                        } label: {
                            nudgeRow(nudge)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .navigationTitle("Nudge Cache")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            nudges = await LLMNudgeCache.shared.allCachedNudges
        }
        .sheet(item: $selectedNudge) { nudge in
            nudgeDetailSheet(nudge)
        }
        .accessibilityIdentifier("debug-nudge-list-view")
    }

    @ViewBuilder
    private func nudgeRow(_ nudge: LLMGeneratedNudge) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(nudge.scheduledTime)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)

                Text(nudge.problemType.icon)

                Text(nudge.problemType.displayName)
                    .font(.caption)
                    .lineLimit(1)

                Spacer()

                Text("LLM")
                    .font(.caption2.bold())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.blue)
                    .clipShape(Capsule())
            }

            Text(nudge.hook)
                .font(.subheadline)
                .lineLimit(1)

            Text(String(nudge.content.prefix(50)) + (nudge.content.count > 50 ? "…" : ""))
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private func nudgeDetailSheet(_ nudge: LLMGeneratedNudge) -> some View {
        NavigationStack {
            List {
                Section("Basic") {
                    row("ID", nudge.id)
                    row("Problem", "\(nudge.problemType.icon) \(nudge.problemType.displayName)")
                    row("Time", nudge.scheduledTime)
                    row("Tone", nudge.tone.rawValue)
                }

                Section("Content") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Hook")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(nudge.hook)
                            .font(.subheadline)
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Content")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(nudge.content)
                            .font(.subheadline)
                    }
                }

                Section("LLM Metadata") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Reasoning")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(nudge.reasoning)
                            .font(.caption)
                    }

                    if let hypothesis = nudge.rootCauseHypothesis {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Root Cause Hypothesis")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(hypothesis)
                                .font(.caption)
                        }
                    }
                }
            }
            .navigationTitle("Nudge Detail")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") {
                        selectedNudge = nil
                    }
                }
            }
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.subheadline)
        }
    }
}

extension LLMGeneratedNudge: @retroactive Identifiable {}
#endif
