import SwiftUI
import StoreKit
import RevenueCat

struct PricingDisclosureBanner: View {
    let billedAmountText: String
    
    var body: some View {
        VStack(spacing: 6) {
            Text(billedAmountText)
                .font(.largeTitle)
                .bold()
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal)
        .padding(.vertical, 12)
    }
}

// Helper to generate billed amount text from Package
extension PricingDisclosureBanner {
    static func billedText(for package: Package) -> String {
        let price = package.storeProduct.localizedPriceString
        if let period = package.storeProduct.subscriptionPeriod {
            switch period.unit {
            case .year:
                return "\(price)/yr"
            case .month:
                return "\(price)/mo"
            case .week:
                return "\(price)/wk"
            default:
                return price
            }
        }
        return price
    }
}

