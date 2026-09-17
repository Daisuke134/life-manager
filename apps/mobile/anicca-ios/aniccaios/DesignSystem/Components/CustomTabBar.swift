import SwiftUI

// 現在は未使用（将来拡張用）
// 標準TabViewのスワイプ・アクセシビリティ保持のため現状は使わない
struct CustomTabBar: View {
    @Binding var selectedTab: Int
    let tabs: [TabItem]

    struct TabItem: Identifiable {
        let id: Int
        let title: String
        let icon: String
        let badge: Int?
    }

    var body: some View {
        HStack(spacing: 0) {
            ForEach(tabs) { tab in
                tabButton(tab)
            }
        }
        .frame(height: 60)
        .background(
            RoundedRectangle(cornerRadius: 0)
                .fill(AppTheme.Colors.cardBackground)
                .shadow(color: .black.opacity(0.1), radius: 4, x: 0, y: -2)
        )
    }

    @ViewBuilder
    private func tabButton(_ tab: TabItem) -> some View {
        let isSelected = selectedTab == tab.id

        Button {
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedTab = tab.id
            }
        } label: {
            VStack(spacing: 4) {
                ZStack {
                    Image(systemName: tab.icon)
                        .font(.system(size: 20))
                        .foregroundStyle(
                            isSelected ? AppTheme.Colors.label : AppTheme.Colors.secondaryLabel
                        )

                    if let badge = tab.badge, badge > 0 {
                        Text("\(badge)")
                            .font(.system(size: 10, weight: .bold))
                            .padding(4)
                            .foregroundColor(.white)
                            .background(Circle().fill(Color.red))
                            .offset(x: 12, y: -12)
                    }
                }

                Text(tab.title)
                    .font(.system(size: 12))
                    .foregroundStyle(
                        isSelected ? AppTheme.Colors.label : AppTheme.Colors.secondaryLabel
                    )
            }
            .frame(maxWidth: .infinity)
            .overlay(
                Rectangle()
                    .fill(isSelected ? AppTheme.Colors.accent : .clear)
                    .frame(height: 2)
                    .offset(y: 28)
            )
        }
        .buttonStyle(.plain)
    }
}










