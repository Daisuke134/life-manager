import SwiftUI
import RevenueCat

/// Older callers share the same pricing and disclosure UI as the current flow.
struct PlanSelectionStepView: View {
    let onPurchaseSuccess: (CustomerInfo) -> Void
    let onDismiss: () -> Void
    let variant: String
    @State private var hasTracked = false

    var body: some View {
        PaywallVariantBView(
            variant: variant,
            onPurchaseSuccess: onPurchaseSuccess,
            onDismiss: onDismiss,
            flowID: "legacy_paywall"
        )
        .analyticsScreen(.paywall, flowID: "legacy_paywall")
        .onAppear {
            guard !hasTracked else { return }
            hasTracked = true
            AnalyticsManager.shared.track(.paywallPlanSelectionViewed, properties: ["presentation_variant": variant])
        }
    }
}
