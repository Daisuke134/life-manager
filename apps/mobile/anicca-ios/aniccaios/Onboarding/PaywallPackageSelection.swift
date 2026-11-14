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
        return offeringCountryCode.uppercased() == currentCountry
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


/// Soft entry applies even while RevenueCat still assigns the retired hard offering.
/// Keep historical identifiers for offering selection and analytics compatibility.
enum PaywallGateVariant: String, Equatable {
    case soft
    case hard

    static let hardOfferingIdentifier = "anicca_variant_b_hard"
    static let experimentIdentifier = "HARD-PAYWALL-20261108"

    static func resolve(offeringIdentifier: String?) -> PaywallGateVariant { .soft }

    static func showsCloseButton(flowID: String, variant: PaywallGateVariant) -> Bool { true }
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
        isUsableForAnicca: (Offering) -> Bool,
        identifier: (Offering) -> String
    ) -> Offering? {
        // A running RevenueCat Experiment delivers the assigned offering as
        // `current`. When that assignment is one of the experiment
        // offerings (control or treatment), it must win over the configured
        // fallback so the A/B split actually reaches the plan screen.
        if let current, isUsableForAnicca(current) {
            let currentIdentifier = identifier(current)
            if currentIdentifier == fallbackIdentifier
                || currentIdentifier == PaywallGateVariant.hardOfferingIdentifier {
                return current
            }
        }
        // The app's plan screen must include its configured Lifetime product,
        // even when the shared current offering points at legacy subscriptions.
        if let configured = all[fallbackIdentifier], isUsableForAnicca(configured) {
            return configured
        }
        if let current, isUsableForAnicca(current) {
            return current
        }
        return nil
    }

    static func isUsableAnicca(productIdentifiers: [String], hasAnnualOrMonthlyPackage: Bool) -> Bool {
        guard hasAnnualOrMonthlyPackage, !productIdentifiers.isEmpty else { return false }
        return productIdentifiers.allSatisfy { $0.hasPrefix("ai.anicca.app.ios.") }
    }
}

/// Unknown eligibility may describe the offer conditionally, but must not promise a free purchase.
enum PaywallTrialPresentation: Equatable {
    case none
    case conditional
    case eligible

    static func resolve(hasFreeTrial: Bool, isEligible: Bool?) -> Self {
        guard hasFreeTrial else { return .none }
        switch isEligible {
        case .some(true): return .eligible
        case .some(false): return .none
        case .none: return .conditional
        }
    }
}
