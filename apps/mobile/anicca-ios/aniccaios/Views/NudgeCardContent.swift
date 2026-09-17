import SwiftUI

/// Nudgeカードのビジュアルレイアウト（iOS/CLI共有）
/// NudgeCardView と ExportableNudgeCardView の両方がこのViewを使う。
/// インタラクティブ要素（ボタン、フィードバック、閉じる）は含まない。
struct NudgeCardContent: View {
    let icon: String
    let title: String
    let hookText: String
    let detailText: String
    let isAIGenerated: Bool

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            // Icon and title
            VStack(spacing: 12) {
                ZStack(alignment: .topTrailing) {
                    Text(icon)
                        .font(.system(size: 48))

                    if isAIGenerated {
                        Circle()
                            .fill(Color.blue.opacity(0.6))
                            .frame(width: 6, height: 6)
                            .offset(x: 8, y: -8)
                            .accessibilityIdentifier("nudge-llm-indicator")
                    }
                }

                Text(title)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(AppTheme.Colors.secondaryLabel)
                    .textCase(.uppercase)
                    .tracking(1)
            }

            // Main quote
            VStack(spacing: 24) {
                Divider()
                    .padding(.horizontal, 40)

                Text(hookText)
                    .font(.system(size: 22, weight: .semibold))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(AppTheme.Colors.label)
                    .padding(.horizontal, 32)
                    .accessibilityIdentifier("nudge-hook-text")

                Divider()
                    .padding(.horizontal, 40)
            }
            .padding(.vertical, 32)

            // Detail text
            Text(detailText)
                .font(.system(size: 16))
                .multilineTextAlignment(.center)
                .foregroundStyle(AppTheme.Colors.secondaryLabel)
                .lineSpacing(6)
                .padding(.horizontal, 40)
                .accessibilityIdentifier("nudge-content-text")
                .accessibilityValue(isAIGenerated ? "llm" : "rule")

            Spacer()
        }
    }
}
