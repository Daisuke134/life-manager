import SwiftUI

struct CardView<Content: View>: View {
    let content: Content
    var cornerRadius: CGFloat = AppTheme.Radius.card
    var backgroundColor: Color? = nil
    var noPadding: Bool = false

    init(
        cornerRadius: CGFloat = AppTheme.Radius.card,
        backgroundColor: Color? = nil,
        noPadding: Bool = false,
        @ViewBuilder content: () -> Content
    ) {
        self.cornerRadius = cornerRadius
        self.backgroundColor = backgroundColor
        self.noPadding = noPadding
        self.content = content()
    }

    var body: some View {
        content
            .padding(noPadding ? 0 : AppTheme.Spacing.lg)
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(backgroundColor ?? AppTheme.Colors.cardBackground)
            )
            .shadow(color: .black.opacity(0.05), radius: 8, x: 0, y: 2)
    }

    static func large(@ViewBuilder content: () -> Content) -> CardView {
        CardView(cornerRadius: AppTheme.Radius.cardLarge, content: content)
    }

    static func xLarge(@ViewBuilder content: () -> Content) -> CardView {
        CardView(cornerRadius: AppTheme.Radius.cardXLarge, content: content)
    }
}




