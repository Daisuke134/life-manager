import SwiftUI

// 曜日選択UI（Mobbin準拠円形48px、4pxボーダー）
struct DayOfWeekPicker: View {
    @Binding var selectedDays: Set<Int>  // 0=日曜日, 1=月曜日, ..., 6=土曜日
    
    private let dayLabels = ["S", "M", "T", "W", "T", "F", "S"]

    var body: some View {
        HStack(spacing: 12) {
            ForEach(0..<7) { index in
                dayButton(for: index)
            }
        }
    }

    @ViewBuilder
    private func dayButton(for index: Int) -> some View {
        let isSelected = selectedDays.contains(index)

        Button {
            if isSelected {
                selectedDays.remove(index)
            } else {
                selectedDays.insert(index)
            }
        } label: {
            Text(dayLabels[index])
                .font(.system(size: 20, weight: .semibold))
                .foregroundColor(
                    isSelected ? AppTheme.Colors.buttonTextSelected : AppTheme.Colors.buttonTextUnselected
                )
                .frame(width: 48, height: 48)
                .background(
                    Circle().fill(
                        isSelected ? AppTheme.Colors.buttonSelected : AppTheme.Colors.buttonUnselected
                    )
                )
                .overlay(
                    Circle().stroke(
                        isSelected ? AppTheme.Colors.border : AppTheme.Colors.borderLight,
                        lineWidth: 4
                    )
                )
        }
        .buttonStyle(.plain)
    }
}

