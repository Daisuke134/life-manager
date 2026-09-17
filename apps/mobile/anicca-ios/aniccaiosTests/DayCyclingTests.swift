import XCTest
@testable import aniccaios

final class DayCyclingTests: XCTestCase {

    // MARK: - Day-Cycling Formula Tests

    func test_dayCycling_day0_slot0_returnsVariant0() {
        // (0 * 3 + 0) % 14 = 0
        let result = calculateDayCyclingVariant(dayIndex: 0, slotIndex: 0, slotsPerDay: 3, variantCount: 14)
        XCTAssertEqual(result, 0)
    }

    func test_dayCycling_day0_slot2_returnsVariant2() {
        // (0 * 3 + 2) % 14 = 2
        let result = calculateDayCyclingVariant(dayIndex: 0, slotIndex: 2, slotsPerDay: 3, variantCount: 14)
        XCTAssertEqual(result, 2)
    }

    func test_dayCycling_day1_slot0_returnsVariant3() {
        // (1 * 3 + 0) % 14 = 3
        let result = calculateDayCyclingVariant(dayIndex: 1, slotIndex: 0, slotsPerDay: 3, variantCount: 14)
        XCTAssertEqual(result, 3)
    }

    func test_dayCycling_day4_slot2_wrapsAround() {
        // (4 * 3 + 2) % 14 = 14 % 14 = 0
        let result = calculateDayCyclingVariant(dayIndex: 4, slotIndex: 2, slotsPerDay: 3, variantCount: 14)
        XCTAssertEqual(result, 0)
    }

    func test_dayCycling_stayingUpLate_day0() {
        // stayingUpLate: 5 slots, 21 variants
        // (0 * 5 + 0) % 21 = 0
        // (0 * 5 + 4) % 21 = 4
        XCTAssertEqual(calculateDayCyclingVariant(dayIndex: 0, slotIndex: 0, slotsPerDay: 5, variantCount: 21), 0)
        XCTAssertEqual(calculateDayCyclingVariant(dayIndex: 0, slotIndex: 4, slotsPerDay: 5, variantCount: 21), 4)
    }

    func test_dayCycling_stayingUpLate_day4_wrapsAround() {
        // (4 * 5 + 1) % 21 = 21 % 21 = 0
        let result = calculateDayCyclingVariant(dayIndex: 4, slotIndex: 1, slotsPerDay: 5, variantCount: 21)
        XCTAssertEqual(result, 0)
    }

    func test_dayCycling_noDuplicatesWithinDay() {
        // 1日内で重複がないことを確認
        for dayIndex in 0..<14 {
            var variants: Set<Int> = []
            for slotIndex in 0..<3 {
                let variant = calculateDayCyclingVariant(dayIndex: dayIndex, slotIndex: slotIndex, slotsPerDay: 3, variantCount: 14)
                XCTAssertFalse(variants.contains(variant), "Day \(dayIndex) has duplicate variant \(variant)")
                variants.insert(variant)
            }
        }
    }

    func test_dayCycling_14days_allVariantsUsed3Times() {
        // 14日間で各バリアントが3回ずつ使われることを確認
        var variantCounts: [Int: Int] = [:]

        for dayIndex in 0..<14 {
            for slotIndex in 0..<3 {
                let variant = calculateDayCyclingVariant(dayIndex: dayIndex, slotIndex: slotIndex, slotsPerDay: 3, variantCount: 14)
                variantCounts[variant, default: 0] += 1
            }
        }

        // 14日 × 3スロット = 42通知, 14バリアント → 各3回
        for variant in 0..<14 {
            XCTAssertEqual(variantCounts[variant], 3, "Variant \(variant) should appear exactly 3 times")
        }
    }

    func test_dayCycling_day14_equals_day0() {
        // Day 15 (dayIndex=14) = Day 1 (dayIndex=0) を確認
        for slotIndex in 0..<3 {
            let day0 = calculateDayCyclingVariant(dayIndex: 0, slotIndex: slotIndex, slotsPerDay: 3, variantCount: 14)
            let day14 = calculateDayCyclingVariant(dayIndex: 14, slotIndex: slotIndex, slotsPerDay: 3, variantCount: 14)
            XCTAssertEqual(day0, day14, "Day 14 slot \(slotIndex) should equal Day 0")
        }
    }

    func test_dayCycling_stayingUpLate_day21_equals_day0() {
        // Day 22 (dayIndex=21) = Day 1 (dayIndex=0) を確認
        for slotIndex in 0..<5 {
            let day0 = calculateDayCyclingVariant(dayIndex: 0, slotIndex: slotIndex, slotsPerDay: 5, variantCount: 21)
            let day21 = calculateDayCyclingVariant(dayIndex: 21, slotIndex: slotIndex, slotsPerDay: 5, variantCount: 21)
            XCTAssertEqual(day0, day21, "Day 21 slot \(slotIndex) should equal Day 0")
        }
    }

    // MARK: - Helper

    private func calculateDayCyclingVariant(dayIndex: Int, slotIndex: Int, slotsPerDay: Int, variantCount: Int) -> Int {
        return (dayIndex * slotsPerDay + slotIndex) % variantCount
    }
}
