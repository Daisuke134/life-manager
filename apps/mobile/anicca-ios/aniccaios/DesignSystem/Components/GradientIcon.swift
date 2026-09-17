import SwiftUI

// ストリークなどの視覚強調用（Mobbin調）
struct GradientIcon: View {
    enum GradientType {
        case fireOrange
        case waterBlue
        case grassGreen
        case sunsetRed

        var colors: [Color] {
            switch self {
            case .fireOrange:
                return [Color(hex: "#FF6B35"), Color(hex: "#FFD23F")]
            case .waterBlue:
                return [Color(hex: "#4ECDC4"), Color(hex: "#44A3F7")]
            case .grassGreen:
                return [Color(hex: "#6BCB77"), Color(hex: "#A8E063")]
            case .sunsetRed:
                return [Color(hex: "#FF6B35"), Color(hex: "#FF3B3B")]
            }
        }
    }

    let gradientType: GradientType
    var size: CGFloat = 60

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.3, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: gradientType.colors,
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: size, height: size)
                .rotationEffect(.degrees(-15))

            RoundedRectangle(cornerRadius: size * 0.25, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            gradientType.colors[0].opacity(0.3),
                            gradientType.colors[1].opacity(0.1)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: size * 0.7, height: size * 0.7)
                .rotationEffect(.degrees(15))
        }
    }
}










