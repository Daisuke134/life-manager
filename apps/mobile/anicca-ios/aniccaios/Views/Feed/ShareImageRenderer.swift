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
                    .font(.system(size: 64, weight: .regular))
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 80)
                    .shadow(color: .black.opacity(0.3), radius: 12, y: 2)
                Spacer()
                Text("aniccaai.com")
                    .font(.system(size: 24, weight: .regular))
                    .foregroundStyle(.white.opacity(0.6))
                    .padding(.bottom, 80)
            }
        }
    }
}
