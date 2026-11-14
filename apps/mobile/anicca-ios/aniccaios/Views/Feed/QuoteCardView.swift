import SwiftUI
import Combine
import StoreKit
import UIKit

/// Today's affirmation; the home owns its background and scrolls only when text needs more room.
struct QuoteCardView: View {
    let quote: Quote
    let pageWidth: CGFloat
    var deliveryId: String? = nil

    @EnvironmentObject var themeStore: ThemeStore
    @EnvironmentObject var likedStore: LikedQuotesStore
    @Environment(\.requestReview) private var requestReview

    @State private var showShareSheet = false
    @State private var copyFlashOpacity: Double = 0
    @ScaledMetric(relativeTo: .title) private var quoteFontSize: CGFloat = 32

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Text(quote.text)
                .font(.system(size: quoteFontSize, weight: .regular, design: .serif))
                .foregroundStyle(themeStore.selected.foregroundColor)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(width: max(120, pageWidth - 64))
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
            ], onComplete: {
                DecisionPointRecorder.shared.recordQuoteResponse(messageId: quote.id, deliveryId: deliveryId, event: .shared)
                AnalyticsManager.shared.track(.affirmationShared, properties: ["quote_id": quote.id, "category": quote.categoryID])
            })
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
                let didFavorite = likedStore.toggle(quote, themeID: themeStore.selected.rawValue)
                AnalyticsManager.shared.track(didFavorite ? .affirmationLiked : .affirmationUnliked, properties: ["quote_id": quote.id, "category": quote.categoryID, "source": "feed"])
                UIImpactFeedbackGenerator(style: .soft).impactOccurred()
                if didFavorite {
                    DecisionPointRecorder.shared.recordQuoteResponse(messageId: quote.id, deliveryId: deliveryId, event: .saved)
                    ReviewPromptCoordinator.shared.requestReviewIfAppropriate {
                        requestReview()
                    }
                }
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
                .foregroundStyle(themeStore.selected.foregroundColor)
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .accessibilityIdentifier(identifier)
    }
}

/// UIActivityViewController wrapper.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    var onComplete: (() -> Void)? = nil
    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: items, applicationActivities: nil)
        controller.completionWithItemsHandler = { _, completed, _, _ in
            if completed { Task { @MainActor in onComplete?() } }
        }
        return controller
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
