import SwiftUI
import Combine
import UIKit

/// One full-screen affirmation card. NO background here — owned by `FeedRootView`.
/// Layout: uniform 26pt centered quote text, wraps naturally; action row centered below.
/// `pageWidth` is the actual visible width passed from FeedRootView so text can hard-clamp
/// to it (works around UIPageViewController giving hosting controllers oversized frames).
struct QuoteCardView: View {
    let quote: Quote
    let pageWidth: CGFloat

    @EnvironmentObject var themeStore: ThemeStore
    @EnvironmentObject var likedStore: LikedQuotesStore

    @State private var showShareSheet = false
    @State private var copyFlashOpacity: Double = 0

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Text(quote.text)
                .font(.system(size: 26, weight: .regular))
                .foregroundStyle(.white)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(width: max(120, pageWidth - 64))
                .shadow(color: .black.opacity(0.35), radius: 10, y: 2)
                .accessibilityIdentifier("quote-text")

            actionRow

            if copyFlashOpacity > 0 {
                Text(String(localized: "quote_copied"))
                    .font(.footnote)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                    .background(.black.opacity(0.4), in: Capsule())
                    .opacity(copyFlashOpacity)
            }

            Spacer()
            Spacer().frame(height: 32)
        }
        .frame(width: pageWidth)
        .sheet(isPresented: $showShareSheet) {
            ShareSheet(items: [
                ShareImageRenderer.render(
                    quote: quote,
                    background: themeStore.selected
                ),
                "aniccaai.com"
            ])
        }
    }

    private var actionRow: some View {
        HStack(spacing: 40) {
            actionButton(systemName: "square.and.arrow.up", identifier: "quote-share") {
                showShareSheet = true
            }

            actionButton(
                systemName: likedStore.isLiked(quote.id) ? "heart.fill" : "heart",
                identifier: "quote-like"
            ) {
                likedStore.toggle(quote.id)
                UIImpactFeedbackGenerator(style: .soft).impactOccurred()
            }

            actionButton(systemName: "doc.on.doc", identifier: "quote-copy") {
                UIPasteboard.general.string = quote.text
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
                withAnimation(.easeOut(duration: 0.2)) { copyFlashOpacity = 1 }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) {
                    withAnimation(.easeIn(duration: 0.4)) { copyFlashOpacity = 0 }
                }
            }
        }
    }

    private func actionButton(systemName: String, identifier: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 22, weight: .regular))
                .foregroundStyle(.white)
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
                .shadow(color: .black.opacity(0.4), radius: 6, y: 1)
        }
        .accessibilityIdentifier(identifier)
    }
}

/// UIActivityViewController wrapper.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
