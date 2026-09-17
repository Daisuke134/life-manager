import SwiftUI

struct AuthRequiredPlaceholderView: View {
    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "person.circle.fill")
                .font(.system(size: 64))
                .foregroundStyle(.secondary)
            
            Text(String(localized: "auth_required_title"))
                .font(.title2)
                .fontWeight(.semibold)
            
            Text(String(localized: "auth_required_message"))
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppBackground())
    }
}




