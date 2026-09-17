import SwiftUI

/// 環境非依存のNudgeCardView（ImageRenderer用）
/// NudgeCardViewと同一レイアウトを保証するため、
/// 共通の中核View（NudgeCardContent）を内部で使用し、
/// ボタンセクション（Primary Action + 👍👎）を追加する。
struct ExportableNudgeCardView: View {
    let problemType: ProblemType
    let notificationTitle: String  // Explicit title (bundle-resolved by CardRenderer)
    let notificationText: String
    let detailText: String
    let positiveButtonText: String  // bundle-resolved by CardRenderer
    let isAIGenerated: Bool
    let language: String  // "en" or "ja"

    var body: some View {
        ZStack {
            AppTheme.Colors.background
                .ignoresSafeArea()

            VStack(spacing: 0) {
                NudgeCardContent(
                    icon: problemType.icon,
                    title: notificationTitle,
                    hookText: notificationText,
                    detailText: detailText,
                    isAIGenerated: isAIGenerated
                )

                // Button section (mirrors NudgeCardView layout)
                VStack(spacing: 24) {
                    Divider()
                        .padding(.horizontal, 40)

                    // Primary Action Button
                    Text(positiveButtonText)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(AppTheme.Colors.buttonSelected)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .padding(.horizontal, 40)

                    Divider()
                        .padding(.horizontal, 40)

                    // Feedback buttons
                    HStack(spacing: 32) {
                        Text("👍")
                            .font(.system(size: 24))
                            .padding(8)
                        Text("👎")
                            .font(.system(size: 24))
                            .padding(8)
                    }
                }
                .padding(.bottom, 40)
            }
        }
        .frame(width: 390, height: 844)
    }
}
