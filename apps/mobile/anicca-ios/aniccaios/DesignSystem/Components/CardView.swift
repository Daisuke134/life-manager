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

extension View {
    /// Shared selection treatment; callers supply the label and trailing checkmark.
    func selectionCard(isSelected: Bool) -> some View {
        self
            .foregroundStyle(AppTheme.Colors.label)
            .background(isSelected ? AppTheme.Colors.accent.opacity(0.12) : AppTheme.Colors.cardBackground.opacity(0.8))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                    .strokeBorder(isSelected ? AppTheme.Colors.accent : .clear, lineWidth: 1)
            }
    }

    func affirmationNavigationTitle(_ title: String) -> some View {
        self
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text(title)
                        .font(AppTheme.Typography.title2Dynamic)
                        .foregroundStyle(AppTheme.Colors.label)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                }
            }
            .tint(AppTheme.Colors.accent)
    }
}
