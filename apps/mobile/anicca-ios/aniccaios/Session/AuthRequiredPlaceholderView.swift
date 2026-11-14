import SwiftUI

struct AuthRequiredPlaceholderView: View {
    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                Image(systemName: "person.circle")
                    .font(.system(size: 64, weight: .ultraLight))
                    .foregroundStyle(AppTheme.Colors.accent)
                    .accessibilityHidden(true)
                Text(String(localized: "auth_required_title"))
                    .font(AppTheme.Typography.title2Dynamic)
                    .accessibilityAddTraits(.isHeader)
                Text(String(localized: "auth_required_message"))
                    .font(.subheadline)
                    .foregroundStyle(AppTheme.Colors.secondaryLabel)
            }
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .foregroundStyle(AppTheme.Colors.label)
            .padding(24)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppBackground())
    }
}
