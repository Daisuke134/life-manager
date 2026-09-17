import SwiftUI

struct AppBackground: View {
    var useOpacity: Bool = false
    
    var body: some View {
        (useOpacity ? AppTheme.Colors.backgroundWithOpacity : AppTheme.Colors.background)
            .ignoresSafeArea()
    }
}
