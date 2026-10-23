//
//  BenYinFanYiAITests.swift
//  BenYinFanYiAITests
//
//  Created by Rork on February 25, 2026.
//

import Testing
import Foundation
@testable import BenYinFanYiAI

struct BenYinFanYiAITests {

    @Test func example() async throws {
        // Write your test here and use APIs like `#expect(...)` to check expected conditions.
    }

}

struct PlanPricingTests {
    @Test func annualSavings_againstWeekly() {
        // ¥1,810/year vs ¥1,300/week × 52
        #expect(PlanPricing.annualSavingsPercent(annual: 1810, periodPrice: 1300, periodsPerYear: 52) == 97)
    }

    @Test func annualSavings_againstMonthly() {
        #expect(PlanPricing.annualSavingsPercent(annual: 29.99, periodPrice: 4.99, periodsPerYear: 12) == 50)
    }

    @Test func annualSavings_nilWhenAnnualNotCheaper() {
        #expect(PlanPricing.annualSavingsPercent(annual: 100, periodPrice: 5, periodsPerYear: 12) == nil)
    }
}
