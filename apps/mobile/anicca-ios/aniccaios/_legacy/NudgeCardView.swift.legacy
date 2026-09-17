import SwiftUI

/// 通知タップ後に表示される1枚画面カード
struct NudgeCardView: View {
    let content: NudgeContent
    let onPositiveAction: () -> Void
    let onNegativeAction: (() -> Void)?
    let onFeedback: (Bool) -> Void // true = 👍, false = 👎
    let onDismiss: () -> Void

    @State private var selectedAction: ActionType?
    @State private var showFeedbackButtons = true

    enum ActionType {
        case positive
        case negative
    }

    var body: some View {
        ZStack {
            // Background
            AppBackground()
                .ignoresSafeArea()

            // Accessibility container for Maestro detection
            Color.clear
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("nudge-card-view")

            VStack(spacing: 0) {
                // Close button
                HStack {
                    Spacer()
                    Button(action: onDismiss) {
                        Image(systemName: "xmark")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundStyle(AppTheme.Colors.secondaryLabel)
                            .padding(12)
                    }
                    .accessibilityIdentifier("nudge-card-close")
                }
                .padding(.horizontal, 8)
                .padding(.top, 8)

                // Shared visual content (iOS/CLI共有)
                NudgeCardContent(
                    icon: content.problemType.icon,
                    title: content.problemType.notificationTitle,
                    hookText: content.notificationText,
                    detailText: content.detailText,
                    isAIGenerated: content.isAIGenerated
                )
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("nudge-card-content")

                // Buttons
                VStack(spacing: 24) {
                    Divider()
                        .padding(.horizontal, 40)

                    // 全ProblemTypeで主ボタン（ポジティブ）を1つだけ表示（選択肢を作らない）
                    primaryActionButtonView

                    Divider()
                        .padding(.horizontal, 40)

                    // Feedback buttons
                    if showFeedbackButtons {
                        feedbackButtonsView
                    } else {
                        Text(String(localized: "feedback_thanks"))
                            .font(.system(size: 16))
                            .foregroundStyle(AppTheme.Colors.secondaryLabel)
                            .accessibilityIdentifier("feedback-submitted")
                    }
                }
                .padding(.bottom, 40)
            }
        }
    }

    // MARK: - Primary Action Button (single, unified style)
    private var primaryActionButtonView: some View {
        Button(action: {
            selectedAction = .positive
            onPositiveAction()
        }) {
            Text(content.problemType.positiveButtonText)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(AppTheme.Colors.buttonSelected)
                .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .accessibilityIdentifier("nudge-primary-action")
        .padding(.horizontal, 40)
    }

    // MARK: - Feedback Buttons
    private var feedbackButtonsView: some View {
        HStack(spacing: 32) {
            Button(action: {
                onFeedback(true)
                // Phase 7+8: contentFeedbackをサーバーに送信
                sendContentFeedback(isPositive: true)
                withAnimation {
                    showFeedbackButtons = false
                }
            }) {
                Text("👍")
                    .font(.system(size: 24))
                    .padding(8)
            }
            .accessibilityIdentifier("feedback-thumbs-up")

            Button(action: {
                onFeedback(false)
                // Phase 7+8: contentFeedbackをサーバーに送信
                sendContentFeedback(isPositive: false)
                withAnimation {
                    showFeedbackButtons = false
                }
            }) {
                Text("👎")
                    .font(.system(size: 24))
                    .padding(8)
            }
            .accessibilityIdentifier("feedback-thumbs-down")
        }
        .opacity(showFeedbackButtons ? 1 : 0)
    }

    // MARK: - Phase 7+8: Content Feedback
    private func sendContentFeedback(isPositive: Bool) {
        guard let nudgeId = content.llmNudgeId else { return }
        Task {
            do {
                try await NudgeFeedbackService.shared.sendContentFeedback(
                    nudgeId: nudgeId,
                    feedback: isPositive ? "thumbsUp" : "thumbsDown",
                    timeSpentSeconds: nil
                )
            } catch {
                // エラーは無視（ユーザー体験を妨げない）
                print("Failed to send content feedback: \(error)")
            }
        }
    }
}

// MARK: - Preview
#Preview {
    let content = NudgeContent.contentForToday(for: .stayingUpLate)
    NudgeCardView(
        content: content,
        onPositiveAction: { print("Positive") },
        onNegativeAction: { print("Negative") },
        onFeedback: { good in print("Feedback: \(good)") },
        onDismiss: { print("Dismiss") }
    )
}
