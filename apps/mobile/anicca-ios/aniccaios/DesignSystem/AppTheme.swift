import SwiftUI

enum AppTheme {
    enum Colors {
        // MARK: - Adaptive Colors (Light/Dark Mode対応)
        
        /// Global accent (monochrome, adapts to dark mode)
        static var accent: Color {
            Color(light: Color(hex: "#222222"), dark: Color(hex: "#e5e5e5"))
        }
        
        /// Main background
        static var background: Color {
            Color(light: Color(hex: "#f8f5ed"), dark: Color(hex: "#1c1b1a"))
        }
        
        /// Background with opacity (for overlays)
        static var backgroundWithOpacity: Color {
            Color(light: Color(red: 246/255, green: 245/255, blue: 236/255, opacity: 0.99),
                  dark: Color(red: 28/255, green: 27/255, blue: 26/255, opacity: 0.99))
        }
        
        /// Card background
        static var cardBackground: Color {
            Color(light: Color(hex: "#fdfcfc"), dark: Color(hex: "#2c2b2a"))
        }
        
        /// Alternative card background
        static var cardBackgroundAlt: Color {
            Color(light: Color(hex: "#fcfcfb"), dark: Color(hex: "#333231"))
        }
        
        /// Primary label color
        static var label: Color {
            Color(light: Color(hex: "#393634"), dark: Color(hex: "#e5e4e2"))
        }
        
        /// Secondary label color
        static var secondaryLabel: Color {
            Color(light: Color(hex: "#898783"), dark: Color(hex: "#a0a09e"))
        }
        
        /// Tertiary label color
        static var tertiaryLabel: Color {
            Color(light: Color(hex: "#b8b6b0"), dark: Color(hex: "#6e6e6c"))
        }
        
        /// Selected button background
        static var buttonSelected: Color {
            Color(light: Color(hex: "#222222"), dark: Color(hex: "#e5e5e5"))
        }
        
        /// Unselected button background
        static var buttonUnselected: Color {
            Color(light: Color(hex: "#e9e6e0"), dark: Color(hex: "#3a3938"))
        }
        
        /// Selected button text
        static var buttonTextSelected: Color {
            Color(light: Color(hex: "#e1e1e1"), dark: Color(hex: "#1c1b1a"))
        }
        
        /// Unselected button text
        static var buttonTextUnselected: Color {
            Color(light: Color(hex: "#898783"), dark: Color(hex: "#a0a09e"))
        }
        
        /// Border color
        static var border: Color {
            Color(light: Color(hex: "#c8c6bf"), dark: Color(hex: "#4a4948"))
        }
        
        /// Light border color
        static var borderLight: Color {
            Color(light: Color(hex: "#f2f0ed"), dark: Color(hex: "#3a3938"))
        }
        
        /// Tab bar background
        static var tabBarBackground: Color {
            Color(light: Color(hex: "#FDFCFC"), dark: Color(hex: "#2c2b2a"))
        }
        
        /// Tab bar selected background
        static var tabBarSelectedBackground: Color {
            Color(light: Color(hex: "#E9E6E0"), dark: Color(hex: "#3a3938"))
        }
        
        /// Tab bar border
        static var tabBarBorder: Color {
            Color(light: Color(red: 200/255, green: 198/255, blue: 191/255, opacity: 0.2),
                  dark: Color(red: 80/255, green: 80/255, blue: 78/255, opacity: 0.3))
        }
        
        // MARK: - Figma準拠カラー (Habits UI)
        
        /// Figma背景色
        static var figmaBackground: Color {
            Color(hex: "#F5F3ED")
        }
        
        /// Figmaカード背景色
        static var figmaCardBackground: Color {
            Color(hex: "#FDFCFA")
        }
        
        /// Figmaアクセントカラー（ゴールド）
        static let habitAccent = Color(red: 0.79, green: 0.70, blue: 0.51) // #C9B382
        
        /// Figmaテキスト色（プライマリ）
        static var figmaTextPrimary: Color {
            Color(hex: "#3A3A3A")
        }
        
        /// Figmaテキスト色（セカンダリ）
        static var figmaTextSecondary: Color {
            Color(hex: "#8A8A82")
        }
        
        // MARK: - Legacy (iOS 14以下のフォールバック用)
        // これらはiOS 15+でadaptiveカラーを使用できない場合のフォールバック
        
        @available(iOS 15.0, *)
        static var adaptiveBackground: Color {
            background
        }
        
        @available(iOS 15.0, *)
        static var adaptiveCardBackground: Color {
            cardBackground
        }
    }
    
    enum Spacing {
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        static let lg: CGFloat = 16
        static let xl: CGFloat = 24
        static let xxl: CGFloat = 32
    }
    
    enum Radius {
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        static let lg: CGFloat = 20
        static let xl: CGFloat = 36
        static let xxl: CGFloat = 76
        
        static let card: CGFloat = 37
        static let cardLarge: CGFloat = 76
        static let cardXLarge: CGFloat = 87
    }
    
    enum Typography {
        // オンボーディングの見出しを全画面で統一（1行収まる最大サイズ想定）
        static let onboardingTitle: Font = .system(size: 36, weight: .heavy)
        
        static let appTitleDynamic: Font = .largeTitle
        static let title2Dynamic: Font = .title2
        static let headlineDynamic: Font = .headline
        static let bodyDynamic: Font = .body
        static let subheadlineDynamic: Font = .subheadline
        static let appTitle: Font = .system(size: 48, weight: .bold)
        static let title2: Font = .system(size: 46, weight: .semibold)
        static let headline: Font = .system(size: 43, weight: .semibold)
        static let body: Font = .system(size: 40, weight: .regular)
        static let subheadline: Font = .system(size: 30, weight: .medium)
        static let footnote: Font = .footnote
        static let caption1Dynamic: Font = .caption
        static let caption2Dynamic: Font = .caption2
    }
}

// MARK: - Color拡張
extension Color {
    /// hex文字列からColorを生成
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
    
    /// Light/Dark mode対応のColor初期化
    init(light: Color, dark: Color) {
        #if canImport(UIKit)
        self.init(uiColor: UIColor { traitCollection in
            traitCollection.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light)
        })
        #elseif canImport(AppKit)
        self.init(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
                ? NSColor(dark) : NSColor(light)
        })
        #else
        self = light
        #endif
    }
}
