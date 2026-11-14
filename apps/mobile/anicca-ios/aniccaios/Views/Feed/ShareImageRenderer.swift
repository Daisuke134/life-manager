import SwiftUI
import Combine
import UIKit

/// Renders a 1080×1920 PNG of a quote on its current theme background, with `aniccaai.com` watermark.
/// The watermark appears ONLY on outbound share assets — never inside the app feed itself.
enum ShareImageRenderer {
    @MainActor
    static func render(quote: Quote, background: ThemeID, size: CGSize = CGSize(width: 1080, height: 1920)) -> UIImage {
        let view = ShareCardView(quote: quote, background: background)
            .frame(width: size.width, height: size.height)
            .clipped()
        let renderer = ImageRenderer(content: view)
        renderer.scale = 1
        return renderer.uiImage ?? UIImage()
    }
}

private struct ShareCardView: View {
    let quote: Quote
    let background: ThemeID

    var body: some View {
        ZStack {
            background.image
                .resizable()
                .scaledToFill()

            VStack {
                Spacer()
                Text(quote.text)
                    .font(.system(size: 64, weight: .regular, design: .serif))
                    .foregroundStyle(background.foregroundColor)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 80)
                Spacer()
                Text(verbatim: "aniccaai.com")
                    .font(.system(size: 24, weight: .regular))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(AppTheme.Colors.accent, in: Capsule())
                    .padding(.bottom, 80)
            }
        }
    }
}
