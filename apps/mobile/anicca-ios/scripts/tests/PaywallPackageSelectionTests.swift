// Standalone native tests of the production helper, without XCTest, StoreKit, or network.
// From apps/mobile/anicca-ios (requires an installed Swift toolchain):
// swiftc -swift-version 5 aniccaios/Onboarding/PaywallPackageSelection.swift \
//   scripts/tests/PaywallPackageSelectionTests.swift -o /tmp/paywall-selection-tests
// /tmp/paywall-selection-tests
// This does not replace SwiftUI/RevenueCat integration tests in Xcode.

private final class TestPackage: Identifiable {
    enum Kind { case annual, monthly, lifetime, weekly }
    let id: String
    let kind: Kind

    init(_ id: String, _ kind: Kind) {
        self.id = id
        self.kind = kind
    }
}

private struct TestOffering {
    let identifier: String
    let productIdentifiers: [String]
    let hasAnnualOrMonthlyPackage: Bool
}

final class PaywallPackageSelectionTests {
    private func resolve(_ packages: [TestPackage], selected: TestPackage? = nil) -> TestPackage? {
        PaywallPackageSelection.resolve(
            packages: packages,
            selectedID: selected?.id,
            isAnnual: { $0.kind == .annual },
            isMonthly: { $0.kind == .monthly }
        )
    }

    private func resolveOffering(_ current: TestOffering?, all: [String: TestOffering]) -> TestOffering? {
        PaywallOfferingSelection.resolve(
            current: current,
            all: all,
            fallbackIdentifier: "anicca_variant_b",
            isUsableForAnicca: {
                PaywallOfferingSelection.isUsableAnicca(
                    productIdentifiers: $0.productIdentifiers,
                    hasAnnualOrMonthlyPackage: $0.hasAnnualOrMonthlyPackage
                )
            }
        )
    }

    private func aniccaOffering(_ identifier: String) -> TestOffering {
        TestOffering(
            identifier: identifier,
            productIdentifiers: ["ai.anicca.app.ios.monthly.b", "ai.anicca.app.ios.yearly.b"],
            hasAnnualOrMonthlyPackage: true
        )
    }

    func testHonneCurrentFallsBackToAniccaVariantB() {
        let honne = TestOffering(
            identifier: "honne_default",
            productIdentifiers: ["com.daisuke.honne.premium.monthly"],
            hasAnnualOrMonthlyPackage: true
        )
        let fallback = aniccaOffering("anicca_variant_b")

        let resolved = resolveOffering(honne, all: ["anicca_variant_b": fallback])

        precondition(resolved?.identifier == "anicca_variant_b")
    }

    func testMissingCurrentFallsBackToAniccaVariantB() {
        let fallback = aniccaOffering("anicca_variant_b")

        let resolved = resolveOffering(nil, all: ["anicca_variant_b": fallback])

        precondition(resolved?.identifier == "anicca_variant_b")
    }

    func testValidAniccaCurrentKeepsRevenueCatTargetingChoice() {
        let targeted = aniccaOffering("anicca_1_8_0_variant_a")
        let fallback = aniccaOffering("anicca_variant_b")

        let resolved = resolveOffering(targeted, all: ["anicca_variant_b": fallback])

        precondition(resolved?.identifier == "anicca_1_8_0_variant_a")
    }

    func testInvalidFallbackNeverReturnsHonneProducts() {
        let honne = TestOffering(
            identifier: "honne_default",
            productIdentifiers: ["com.daisuke.honne.premium.monthly"],
            hasAnnualOrMonthlyPackage: true
        )

        let resolved = resolveOffering(honne, all: ["anicca_variant_b": honne])

        precondition(resolved == nil)
    }

    func testAniccaOfferingMustContainOnlyAniccaProductsAndMonthlyOrAnnualPlan() {
        let products = ["ai.anicca.app.ios.monthly.b", "ai.anicca.app.ios.yearly.b"]
        precondition(PaywallOfferingSelection.isUsableAnicca(productIdentifiers: products, hasAnnualOrMonthlyPackage: true))
        precondition(!PaywallOfferingSelection.isUsableAnicca(productIdentifiers: products + ["com.daisuke.honne.premium.monthly"], hasAnnualOrMonthlyPackage: true))
        precondition(!PaywallOfferingSelection.isUsableAnicca(productIdentifiers: products, hasAnnualOrMonthlyPackage: false))
        precondition(!PaywallOfferingSelection.isUsableAnicca(productIdentifiers: [], hasAnnualOrMonthlyPackage: true))
    }

    func testFreshCustomerInfoOverridesStaleCachedEntitlement() {
        precondition(OnboardingPaywallDecision.resolve(freshEntitlement: true, cachedEntitlement: false) == .completeOnboarding)
        precondition(OnboardingPaywallDecision.resolve(freshEntitlement: false, cachedEntitlement: true) == .presentPaywall)
    }

    func testUnavailableCustomerInfoFallsBackToCachedEntitlement() {
        precondition(OnboardingPaywallDecision.resolve(freshEntitlement: nil, cachedEntitlement: true) == .completeOnboarding)
        precondition(OnboardingPaywallDecision.resolve(freshEntitlement: nil, cachedEntitlement: false) == .presentPaywall)
    }

    func testDelayedLoadSelectsAnnualWithoutAnotherAppearance() {
        var selected = resolve([])
        precondition(selected == nil)
        let annual = TestPackage("annual", .annual)
        let monthly = TestPackage("monthly", .monthly)

        selected = resolve([monthly, annual], selected: selected)

        precondition(selected === annual)
    }

    func testMonthlyOnlyLoadSelectsMonthly() {
        let monthly = TestPackage("monthly", .monthly)
        precondition(resolve([monthly]) === monthly)
    }

    func testUserMonthlyChoiceSurvivesRefreshAndRebindsToCurrentInstance() {
        let oldMonthly = TestPackage("monthly", .monthly)
        let newMonthly = TestPackage("monthly", .monthly)
        let annual = TestPackage("annual", .annual)

        let selected = resolve([annual, newMonthly], selected: oldMonthly)

        precondition(selected === newMonthly)
        precondition(selected !== oldMonthly)
    }

    func testAnnualReplacementRebindsToCurrentInstance() {
        let oldAnnual = TestPackage("annual", .annual)
        let newAnnual = TestPackage("annual", .annual)
        precondition(resolve([newAnnual], selected: oldAnnual) === newAnnual)
    }

    func testExplicitLifetimeChoiceSurvivesRefresh() {
        let lifetime = TestPackage("lifetime", .lifetime)
        let annual = TestPackage("annual", .annual)
        precondition(resolve([annual, lifetime], selected: lifetime) === lifetime)
    }

    func testRemovedSelectionFallsBackToAnnualThenMonthly() {
        let removed = TestPackage("removed", .monthly)
        let annual = TestPackage("annual", .annual)
        let monthly = TestPackage("monthly", .monthly)
        precondition(resolve([monthly, annual], selected: removed) === annual)
        precondition(resolve([monthly], selected: removed) === monthly)
    }

    func testEmptyRefreshClearsSelectionAndRetryChoosesAvailableDefault() {
        let oldMonthly = TestPackage("monthly", .monthly)
        var selected = resolve([], selected: oldMonthly)
        precondition(selected == nil)
        let annual = TestPackage("annual", .annual)
        let monthly = TestPackage("monthly", .monthly)

        selected = resolve([monthly, annual], selected: selected)

        precondition(selected === annual)
    }

    func testNoAnnualOrMonthlyDoesNotInventADefault() {
        let lifetime = TestPackage("lifetime", .lifetime)
        let weekly = TestPackage("weekly", .weekly)
        precondition(resolve([lifetime, weekly]) == nil)
        precondition(resolve([lifetime], selected: TestPackage("removed", .annual)) == nil)
    }

    func testLifetimeIsAvailableOnlyForMatchingStorefrontOffering() {
        precondition(PaywallStorefrontEligibility.includesLifetime(countryCode: "JPN", offeringCountryCode: "JPN"))
        precondition(PaywallStorefrontEligibility.includesLifetime(countryCode: "jpn", offeringCountryCode: "jpn"))
        precondition(!PaywallStorefrontEligibility.includesLifetime(countryCode: "USA", offeringCountryCode: "JPN"))
        precondition(PaywallStorefrontEligibility.includesLifetime(countryCode: "GBR", offeringCountryCode: "GBR"))
        precondition(!PaywallStorefrontEligibility.includesLifetime(countryCode: nil, offeringCountryCode: "JPN"))
        precondition(!PaywallStorefrontEligibility.includesLifetime(countryCode: "JPN", offeringCountryCode: nil))
        precondition(!PaywallStorefrontEligibility.includesLifetime(countryCode: "JPN", offeringCountryCode: "USA"))
    }

    func testLifetimePurchaseChecksTheLiveStorefrontAndKeepsOtherPlansAvailable() {
        precondition(PaywallStorefrontEligibility.allowsPurchase(
            packageIsLifetime: true,
            packageIsCurrent: true,
            countryCode: "JPN",
            offeringCountryCode: "JPN"
        ))
        precondition(!PaywallStorefrontEligibility.allowsPurchase(
            packageIsLifetime: true,
            packageIsCurrent: true,
            countryCode: "USA",
            offeringCountryCode: "JPN"
        ))
        precondition(!PaywallStorefrontEligibility.allowsPurchase(
            packageIsLifetime: true,
            packageIsCurrent: true,
            countryCode: "JPN",
            offeringCountryCode: nil
        ))
        precondition(PaywallStorefrontEligibility.allowsPurchase(
            packageIsLifetime: false,
            packageIsCurrent: true,
            countryCode: "USA",
            offeringCountryCode: nil
        ))
        precondition(!PaywallStorefrontEligibility.allowsPurchase(
            packageIsLifetime: false,
            packageIsCurrent: false,
            countryCode: "USA",
            offeringCountryCode: "USA"
        ))
    }

    func testOfferingRefreshRejectsOlderCompletionAndStorefrontChanges() {
        precondition(PaywallOfferingSelection.isLatestRefresh(requestID: 3, currentRequestID: 3))
        precondition(!PaywallOfferingSelection.isLatestRefresh(requestID: 2, currentRequestID: 3))
        precondition(PaywallOfferingSelection.isUnchangedStorefrontRevision(startingRevision: 4, currentRevision: 4))
        precondition(!PaywallOfferingSelection.isUnchangedStorefrontRevision(startingRevision: 4, currentRevision: 6))
        precondition(PaywallStorefrontEligibility.sameStorefront(first: "jpn", second: "JPN"))
        precondition(PaywallStorefrontEligibility.sameStorefront(first: nil, second: nil))
        precondition(!PaywallStorefrontEligibility.sameStorefront(first: "USA", second: "JPN"))
        precondition(!PaywallStorefrontEligibility.sameStorefront(first: nil, second: "JPN"))
    }

    func testStorefrontRevisionRejectsJapanUsaJapanRoundTrip() {
        let startingRevision = 10
        let revisionAfterJapanToUsaToJapan = 12
        precondition(!PaywallOfferingSelection.isUnchangedStorefrontRevision(
            startingRevision: startingRevision,
            currentRevision: revisionAfterJapanToUsaToJapan
        ))
    }

    func testPurchaseRequiresTheSelectedPackageInstanceFromTheCurrentOffering() {
        let current = TestPackage("current", .lifetime)
        let stale = TestPackage("current", .lifetime)
        precondition(PaywallPackageSelection.containsCurrentInstance(current, in: [current]))
        precondition(!PaywallPackageSelection.containsCurrentInstance(stale, in: [current]))
    }

    func testRepeatedRefreshKeepsUserSelection() {
        let annual = TestPackage("annual", .annual)
        let monthly = TestPackage("monthly", .monthly)
        var selected: TestPackage? = monthly
        for _ in 0..<3 {
            selected = resolve([annual, monthly], selected: selected)
            precondition(selected === monthly)
        }
    }

    var allTests: [(String, () -> Void)] { [
        ("testHonneCurrentFallsBackToAniccaVariantB", testHonneCurrentFallsBackToAniccaVariantB),
        ("testMissingCurrentFallsBackToAniccaVariantB", testMissingCurrentFallsBackToAniccaVariantB),
        ("testValidAniccaCurrentKeepsRevenueCatTargetingChoice", testValidAniccaCurrentKeepsRevenueCatTargetingChoice),
        ("testInvalidFallbackNeverReturnsHonneProducts", testInvalidFallbackNeverReturnsHonneProducts),
        ("testAniccaOfferingMustContainOnlyAniccaProductsAndMonthlyOrAnnualPlan", testAniccaOfferingMustContainOnlyAniccaProductsAndMonthlyOrAnnualPlan),
        ("testFreshCustomerInfoOverridesStaleCachedEntitlement", testFreshCustomerInfoOverridesStaleCachedEntitlement),
        ("testUnavailableCustomerInfoFallsBackToCachedEntitlement", testUnavailableCustomerInfoFallsBackToCachedEntitlement),
        ("testDelayedLoadSelectsAnnualWithoutAnotherAppearance", testDelayedLoadSelectsAnnualWithoutAnotherAppearance),
        ("testMonthlyOnlyLoadSelectsMonthly", testMonthlyOnlyLoadSelectsMonthly),
        ("testUserMonthlyChoiceSurvivesRefreshAndRebindsToCurrentInstance", testUserMonthlyChoiceSurvivesRefreshAndRebindsToCurrentInstance),
        ("testAnnualReplacementRebindsToCurrentInstance", testAnnualReplacementRebindsToCurrentInstance),
        ("testExplicitLifetimeChoiceSurvivesRefresh", testExplicitLifetimeChoiceSurvivesRefresh),
        ("testRemovedSelectionFallsBackToAnnualThenMonthly", testRemovedSelectionFallsBackToAnnualThenMonthly),
        ("testEmptyRefreshClearsSelectionAndRetryChoosesAvailableDefault", testEmptyRefreshClearsSelectionAndRetryChoosesAvailableDefault),
        ("testNoAnnualOrMonthlyDoesNotInventADefault", testNoAnnualOrMonthlyDoesNotInventADefault),
        ("testLifetimeIsAvailableOnlyForMatchingStorefrontOffering", testLifetimeIsAvailableOnlyForMatchingStorefrontOffering),
        ("testLifetimePurchaseChecksTheLiveStorefrontAndKeepsOtherPlansAvailable", testLifetimePurchaseChecksTheLiveStorefrontAndKeepsOtherPlansAvailable),
        ("testOfferingRefreshRejectsOlderCompletionAndStorefrontChanges", testOfferingRefreshRejectsOlderCompletionAndStorefrontChanges),
        ("testStorefrontRevisionRejectsJapanUsaJapanRoundTrip", testStorefrontRevisionRejectsJapanUsaJapanRoundTrip),
        ("testPurchaseRequiresTheSelectedPackageInstanceFromTheCurrentOffering", testPurchaseRequiresTheSelectedPackageInstanceFromTheCurrentOffering),
        ("testRepeatedRefreshKeepsUserSelection", testRepeatedRefreshKeepsUserSelection),
    ] }
}

@main
enum PaywallPackageSelectionTestRunner {
    static func main() {
        let tests = PaywallPackageSelectionTests().allTests
        for (name, run) in tests {
            run()
            print("PASS \(name)")
        }
        print("\(tests.count) native selection regressions passed")
    }
}
