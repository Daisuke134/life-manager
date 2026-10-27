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

    static func containsCurrentInstance<Candidate: AnyObject>(_ candidate: Candidate, in candidates: [Candidate]) -> Bool {
        candidates.contains { $0 === candidate }
    }
}

/// Fails closed unless both the App Store region and its refreshed offering are known.
enum PaywallStorefrontEligibility {
    static func sameStorefront(first: String?, second: String?) -> Bool {
        first?.uppercased() == second?.uppercased()
    }

    static func includesLifetime(countryCode: String?, offeringCountryCode: String?) -> Bool {
        guard let countryCode, let offeringCountryCode else { return false }
        let currentCountry = countryCode.uppercased()
        return currentCountry == "JPN" && offeringCountryCode.uppercased() == currentCountry
    }

    static func allowsPurchase(
        packageIsLifetime: Bool,
        packageIsCurrent: Bool,
        countryCode: String?,
        offeringCountryCode: String?
    ) -> Bool {
        packageIsCurrent && (!packageIsLifetime || includesLifetime(
            countryCode: countryCode,
            offeringCountryCode: offeringCountryCode
        ))
    }
}


enum PaywallOfferingSelection {
    static func isLatestRefresh(requestID: Int, currentRequestID: Int) -> Bool {
        requestID == currentRequestID
    }

    static func isUnchangedStorefrontRevision(startingRevision: Int, currentRevision: Int) -> Bool {
        startingRevision == currentRevision
    }

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

enum OnboardingPaywallDecision: Equatable {
    case completeOnboarding
    case presentPaywall

    static func resolve(freshEntitlement: Bool?, cachedEntitlement: Bool) -> Self {
        guard let freshEntitlement else {
            return cachedEntitlement ? .completeOnboarding : .presentPaywall
        }
        return freshEntitlement ? .completeOnboarding : .presentPaywall
    }
}
