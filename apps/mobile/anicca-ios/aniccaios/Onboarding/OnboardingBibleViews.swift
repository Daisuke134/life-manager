import SwiftUI
import RevenueCat

// MARK: - Optional Paywall

struct PaywallFlowContainer: View {
    let onPurchaseSuccess: (CustomerInfo) -> Void
    let onDismiss: () -> Void
    var flowID: String = "onboarding"
    @State private var step: PaywallStep = .planSelection
    @EnvironmentObject private var appState: AppState

    var body: some View {
        ZStack(alignment: .topTrailing) {
            AppBackground()

            switch step {
            case .primer:
                PaywallPrimerStepView(next: { step = .planSelection })
            case .planSelection:
                PaywallVariantBView(
                    variant: "b",
                    onPurchaseSuccess: onPurchaseSuccess,
                    onDismiss: onDismiss,
                    flowID: flowID
                )
            }

            Group {
                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(.secondary)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .accessibilityIdentifier("paywall-close-button")
                .accessibilityLabel(Text(String(localized: "common_close")))
                .padding(.trailing, 12)
                .padding(.top, 8)
            }
        }
        .analyticsScreen(.paywall, flowID: flowID)
    }
}
