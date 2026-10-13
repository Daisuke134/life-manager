/// Reconciles a paywall choice against the latest available package instances.
/// Kept independent of RevenueCat so selection can be tested without StoreKit.
enum PaywallPackageSelection {
    static func resolve<Candidate: Identifiable>(
        packages: [Candidate],
        selectedID: Candidate.ID?,
        isAnnual: (Candidate) -> Bool,
        isMonthly: (Candidate) -> Bool
    ) -> Candidate? {
        if let selectedID,
           let current = packages.first(where: { $0.id == selectedID }) {
            return current
        }

        return packages.first(where: isAnnual) ?? packages.first(where: isMonthly)
    }
}


enum PaywallOfferingSelection {
    static func resolve<Offering>(
        current: Offering?,
        all: [String: Offering],
        fallbackIdentifier: String,
        isUsableForAnicca: (Offering) -> Bool
    ) -> Offering? {
        if let current, isUsableForAnicca(current) {
            return current
        }

        guard let fallback = all[fallbackIdentifier], isUsableForAnicca(fallback) else {
            return nil
        }
        return fallback
    }

    static func isUsableAnicca(productIdentifiers: [String], hasAnnualOrMonthlyPackage: Bool) -> Bool {
        guard hasAnnualOrMonthlyPackage, !productIdentifiers.isEmpty else { return false }
        return productIdentifiers.allSatisfy { $0.hasPrefix("ai.anicca.app.ios.") }
    }
}
