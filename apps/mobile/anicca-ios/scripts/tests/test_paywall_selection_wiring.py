"""Static SwiftUI wiring contracts; these do not execute Swift or RevenueCat.

Run from any directory with Python 3. Native selection behavior is covered by
PaywallPackageSelectionTests.swift alongside this file.
"""

from pathlib import Path
import re
import unittest


APP_ROOT = Path(__file__).resolve().parents[2]
VIEW = APP_ROOT / "aniccaios/Onboarding/PaywallVariantBView.swift"
HELPER = APP_ROOT / "aniccaios/Onboarding/PaywallPackageSelection.swift"
SUBSCRIPTION_MANAGER = APP_ROOT / "aniccaios/Services/SubscriptionManager.swift"


class PaywallSelectionWiringTests(unittest.TestCase):
    def setUp(self):
        self.source = VIEW.read_text(encoding="utf-8")
        self.helper = HELPER.read_text(encoding="utf-8")

    def test_offering_load_rejects_honne_current_and_falls_back_to_anicca_variant_b(self):
        manager = SUBSCRIPTION_MANAGER.read_text(encoding="utf-8")
        for required in (
            'private static let aniccaFallbackOfferingIdentifier = "anicca_variant_b"',
            "PaywallOfferingSelection.resolve(",
            "isUsableForAnicca:",
            'productIdentifiers: packages.map { $0.storeProduct.productIdentifier }',
            "resolveAniccaOffering(from: cached)",
            "resolveAniccaOffering(from: result)",
        ):
            self.assertIn(required, manager)
        self.assertIn('productIdentifiers.allSatisfy { $0.hasPrefix("ai.anicca.app.ios.") }', self.helper)
        self.assertNotIn("if let offering = result.current", manager)

    def test_initial_appearance_reconciles_selection(self):
        self.assertIsNotNone(re.search(
            r"(?s)\.onAppear\s*\{\s*if !hasTracked\s*\{.*?\}"
            r"\s*synchronizePackageSelection\(\)\s*\}",
            self.source,
        ), "Initial appearance must reconcile selection")

    def test_async_load_and_same_id_replacement_reconcile_selection(self):
        # IDs and Package's value equality can stay the same on a refresh.
        # Observing object identity must still select the new Package instance.
        self.assertIsNotNone(re.search(
            r"(?s)\.onChange\(of: packages\.map\s*\{\s*ObjectIdentifier\(\$0\)"
            r"\s*\}\)\s*\{\s*_ in\s*synchronizePackageSelection\(\)\s*\}",
            self.source,
        ), "Package instance changes must reconcile selection after load or retry")

    def test_reconciliation_passes_current_packages_and_user_selection(self):
        match = re.search(
            r"(?s)private func synchronizePackageSelection\(\)\s*\{(.*?)\n    \}",
            self.source,
        )
        self.assertIsNotNone(match, "The view must reconcile asynchronously loaded packages")
        body = match.group(1)
        for required in (
            "selectedPackage = PaywallPackageSelection.resolve(",
            "packages: packages,",
            "selectedID: selectedPackage?.id,",
            "isAnnual: { $0.packageType == .annual },",
            "isMonthly: { $0.packageType == .monthly }",
        ):
            self.assertIn(required, body)
        for forbidden in ("Purchases.", "purchase()", "isPurchasing =", "onDismiss(", "onPurchaseSuccess("):
            self.assertNotIn(forbidden, body)

    def test_purchase_requires_selection_and_blocks_repeated_cta_taps(self):
        self.assertIn(".disabled(selectedPackage == nil || isPurchasing)", self.source)
        self.assertRegex(
            self.source,
            r"private func purchase\(\)\s*\{\s*guard let package = selectedPackage else \{ return \}",
        )
        self.assertIn("Button { purchase() } label:", self.source)

    def test_lifetime_is_gated_by_current_app_store_storefront(self):
        self.assertIn("import StoreKit", self.source)
        self.assertIn("await Storefront.current", self.source)
        self.assertIn("AsyncStream<Void>", self.source)
        self.assertIn("for await storefront in Storefront.updates", self.source)
        self.assertIn("await Task.yield()", self.source)
        self.assertIn("latestStorefront?.countryCode.uppercased() == countryCode?.uppercased()", self.source)
        self.assertIn("PaywallStorefrontEligibility.includesLifetime(", self.source)
        purchase = self.source.split("private func purchase()", 1)[1].split("private func restorePurchases()", 1)[0]
        self.assertIn("let currentStorefront = isLifetimePackage ? await Storefront.current : nil", purchase)
        self.assertIn("PaywallStorefrontEligibility.allowsPurchase(", purchase)
        self.assertLess(purchase.index("PaywallStorefrontEligibility.allowsPurchase("), purchase.index("Purchases.shared.purchase(package: package)"))
        self.assertIn("containsCurrentInstance(package, in: currentPackages)", purchase)
        self.assertIn("appState.cachedOfferingStorefrontCountryCode", self.source)
        self.assertNotIn("Locale.preferredLanguages", self.source)

    def test_retry_and_timeout_recheck_storefront_eligibility(self):
        retry = self.source.split('Button(String(localized: "paywall_b_retry"))', 1)[1].split(
            'Button(String(localized: "paywall_plan_restore"))', 1
        )[0]
        self.assertIn("Task { await refreshStorefrontEligibility() }", retry)
        timeout = self.source.split("private func scheduleReloadTimeout()", 1)[1].split("private func purchase()", 1)[0]
        self.assertIn("Task { await refreshStorefrontEligibility() }", timeout)

    def test_subscription_refresh_discards_outdated_and_cross_storefront_results(self):
        manager = SUBSCRIPTION_MANAGER.read_text(encoding="utf-8")
        self.assertIn("offeringsRefreshGeneration", manager)
        self.assertIn("PaywallOfferingSelection.isLatestRefresh(", manager)
        self.assertIn("PaywallStorefrontEligibility.sameStorefront(", manager)
        self.assertLess(manager.index("PaywallOfferingSelection.isLatestRefresh("), manager.index("AppState.shared.updateOffering(aniccaOffering"))

    def test_storefront_revision_rejects_roundtrip_and_purchase_time_races(self):
        app_state = (APP_ROOT / "aniccaios/AppState.swift").read_text(encoding="utf-8")
        manager = SUBSCRIPTION_MANAGER.read_text(encoding="utf-8")
        self.assertIn("@Published private(set) var storefrontRevision", app_state)
        self.assertIn("func recordStorefrontCountryCode(", app_state)
        refresh = manager.split("func refreshOfferings()", 1)[1].split("func syncNow()", 1)[0]
        self.assertIn("let requestStorefrontRevision = AppState.shared.storefrontRevision", refresh)
        self.assertIn("isUnchangedStorefrontRevision(", refresh)
        self.assertLess(refresh.index("isUnchangedStorefrontRevision("), refresh.index("updateOffering(aniccaOffering"))
        self.assertIn("AppState.shared.recordStorefrontCountryCode(storefront.countryCode)", self.source)
        purchase = self.source.split("private func purchase()", 1)[1].split("private func restorePurchases()", 1)[0]
        self.assertIn("let purchaseStorefrontRevision = appState.storefrontRevision", purchase)
        self.assertIn("isUnchangedStorefrontRevision(", purchase)
        self.assertIn("appState.currentStorefrontCountryCode", purchase)
        self.assertIn("Task { @MainActor in", purchase)
        self.assertNotIn("await MainActor.run", purchase)

    def test_policy_returns_current_match_before_annual_monthly_defaults(self):
        # Structural contract only. Execute the companion Swift tests to verify
        # actual selection behavior and reference identity in the Swift runtime.
        helper = HELPER.read_text(encoding="utf-8")
        self.assertIsNotNone(re.search(
            r"(?s)if let selectedID,\s*let current = packages\.first\(where:"
            r"\s*\{\s*\$0\.id == selectedID\s*\}\)\s*\{\s*return current\s*\}"
            r"\s*return packages\.first\(where: isAnnual\)"
            r"\s*\?\? packages\.first\(where: isMonthly\)",
            helper,
        ), "Preserve only a current instance, then prefer annual over monthly")


if __name__ == "__main__":
    unittest.main()
## tests complete
