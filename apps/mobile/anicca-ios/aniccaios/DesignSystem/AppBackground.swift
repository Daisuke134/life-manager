import SwiftUI

struct AppBackground: View {
    var useOpacity: Bool = false

    var body: some View {
        LinearGradient(
            colors: [AppTheme.Colors.background,
                     Color(light: Color(hex: "#E3E9DA"), dark: Color(hex: "#26392D"))],
            startPoint: .topTrailing,
            endPoint: .bottomLeading
        )
        .opacity(useOpacity ? 0.99 : 1)
        .ignoresSafeArea()
    }
}
