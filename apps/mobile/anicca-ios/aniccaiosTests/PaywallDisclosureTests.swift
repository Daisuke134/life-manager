import XCTest
@testable import aniccaios

final class PaywallDisclosureTests: XCTestCase {
    func testFreeTrialRequiresThisProductsOfferAndConfirmedEligibility() {
        XCTAssertEqual(PaywallTrialPresentation.resolve(hasFreeTrial: true, isEligible: true), .eligible)
        XCTAssertEqual(PaywallTrialPresentation.resolve(hasFreeTrial: true, isEligible: false), .none)
    }

    func testUnknownEligibilityKeepsTheOfferConditional() {
        XCTAssertEqual(PaywallTrialPresentation.resolve(hasFreeTrial: true, isEligible: nil), .conditional)
    }

    func testLifetimeOrAnotherProductWithoutAFreeTrialCannotInheritAnAnnualTrial() {
        for eligibility in [true, false, nil] as [Bool?] {
            XCTAssertEqual(PaywallTrialPresentation.resolve(hasFreeTrial: false, isEligible: eligibility), .none)
        }
    }
}
