import SwiftUI
import UIKit

struct PrimaryButton: View {
    let title: String
    var icon: String? = nil
    var isEnabled: Bool = true
    var isLoading: Bool = false
    var style: ButtonStyle = .primary
    let action: () -> Void

    enum ButtonStyle {
        case primary
        case selected
        case unselected
        case large
    }

    var body: some View {
        Button {
            guard isEnabled, !isLoading else { return }
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            action()
        } label: {
            HStack(spacing: 8) {
                if isLoading {
                    ProgressView().progressViewStyle(.circular)
                } else if let icon {
                    Image(systemName: icon)
                }
                Text(title)
                    .font(.headline)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 64)  // HTML仕様: h-16 = 64pt
        }
        .foregroundStyle(foregroundColor)
        .background(
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(backgroundColor)
        )
        .overlay(
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .stroke(borderColor, lineWidth: borderWidth)
        )
        .opacity(isEnabled ? 1 : 0.6)
        .disabled(!isEnabled || isLoading)
    }

    private var backgroundColor: Color {
        switch style {
        case .primary, .large:
            return AppTheme.Colors.accent
        case .selected:
            return AppTheme.Colors.buttonSelected
        case .unselected:
            return AppTheme.Colors.buttonUnselected
        }
    }

    private var foregroundColor: Color {
        switch style {
        case .primary, .large:
            return AppTheme.Colors.buttonTextSelected  // .white から変更
        case .selected:
            return AppTheme.Colors.buttonTextSelected
        case .unselected:
            return AppTheme.Colors.buttonTextUnselected
        }
    }

    private var cornerRadius: CGFloat {
        switch style {
        case .primary:
            return AppTheme.Radius.xxl  // 丸角に変更
        case .selected, .unselected:
            return .infinity  // 完全な丸(Capsule)
        case .large:
            return .infinity  // 完全な丸(Capsule)
        }
    }

    private var borderColor: Color {
        switch style {
        case .primary, .large:
            return .clear
        case .selected:
            return AppTheme.Colors.border
        case .unselected:
            return AppTheme.Colors.borderLight
        }
    }

    private var borderWidth: CGFloat {
        switch style {
        case .primary, .large:
            return 0
        case .selected, .unselected:
            return 4
        }
    }
}



