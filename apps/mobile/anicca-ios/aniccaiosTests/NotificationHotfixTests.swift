import XCTest
@testable import aniccaios

/// v1.6.0 通知頻度リデザインテスト
/// 1問題あたり3回/日（夜更かしのみ5回）、最低15分間隔
@MainActor
final class NotificationHotfixTests: XCTestCase {

    // MARK: - v1.6.0: 全41スロットがユニーク（バッティングゼロ）

    func test_allTimeSlotsAreUnique() {
        // 全13問題のスロットを収集
        var allSlots: [(problem: ProblemType, hour: Int, minute: Int)] = []
        for problem in ProblemType.allCases {
            for slot in problem.notificationSchedule {
                allSlots.append((problem: problem, hour: slot.hour, minute: slot.minute))
            }
        }

        // 時刻の重複チェック
        var seen: Set<String> = []
        var duplicates: [String] = []
        for slot in allSlots {
            let key = "\(slot.hour):\(String(format: "%02d", slot.minute))"
            if seen.contains(key) {
                duplicates.append("\(key) (\(slot.problem.rawValue))")
            }
            seen.insert(key)
        }

        XCTAssertTrue(duplicates.isEmpty, "Duplicate time slots found: \(duplicates.joined(separator: ", "))")
    }

    func test_totalSlotCountIs41() {
        // v1.6.0: 5 + 3*12 = 41スロット
        let total = ProblemType.allCases.reduce(0) { $0 + $1.notificationSchedule.count }
        XCTAssertEqual(total, 41, "Total slots should be 41 (5 + 3×12)")
    }

    // MARK: - v1.6.0: スロット間の最低間隔（15分以上）

    func test_minimumGapBetweenSlots_is15minutes() {
        var allSlots: [(minutes: Int, problem: String)] = []
        for problem in ProblemType.allCases {
            for slot in problem.notificationSchedule {
                // 翌日スロット（0:00-5:59）は +1440 で計算
                let mins = slot.hour < 6 ? slot.hour * 60 + slot.minute + 1440 : slot.hour * 60 + slot.minute
                allSlots.append((minutes: mins, problem: problem.rawValue))
            }
        }
        allSlots.sort { $0.minutes < $1.minutes }

        for i in 1..<allSlots.count {
            let gap = allSlots[i].minutes - allSlots[i-1].minutes
            XCTAssertGreaterThanOrEqual(gap, 15,
                "Gap between \(allSlots[i-1].problem)@\(allSlots[i-1].minutes) and \(allSlots[i].problem)@\(allSlots[i].minutes) is only \(gap) minutes")
        }
    }

    // MARK: - v1.6.0: 同一問題内の最低間隔（30分以上、cantWakeUp wake window除く）

    func test_sameProblemGap_minimum30minutes() {
        for problem in ProblemType.allCases {
            let slots = problem.notificationSchedule.map { slot -> Int in
                slot.hour < 6 ? slot.hour * 60 + slot.minute + 1440 : slot.hour * 60 + slot.minute
            }.sorted()

            for i in 1..<slots.count {
                let gap = slots[i] - slots[i-1]
                // cantWakeUp wake window (6:00-7:15) は30分未満許可
                if problem == .cantWakeUp && slots[i-1] >= 360 && slots[i] <= 435 {
                    XCTAssertGreaterThanOrEqual(gap, 30,
                        "\(problem.rawValue): gap between slots \(slots[i-1]) and \(slots[i]) is \(gap)min")
                } else {
                    XCTAssertGreaterThanOrEqual(gap, 30,
                        "\(problem.rawValue): gap between slots \(slots[i-1]) and \(slots[i]) is \(gap)min (minimum 30)")
                }
            }
        }
    }

    // MARK: - P2: validTimeRange

    func test_validTimeRange_sleepProblems() {
        // staying_up_late: 6:00-01:30
        let sul = ProblemType.stayingUpLate.validTimeRange
        XCTAssertNotNil(sul)
        XCTAssertEqual(sul?.startHour, 6)
        XCTAssertEqual(sul?.startMinute, 0)
        XCTAssertEqual(sul?.endHour, 1)
        XCTAssertEqual(sul?.endMinute, 31)

        // porn_addiction: 6:00-01:31 (exclusive, includes 1:30 slot)
        let pa = ProblemType.pornAddiction.validTimeRange
        XCTAssertNotNil(pa)
        XCTAssertEqual(pa?.startHour, 6)
        XCTAssertEqual(pa?.endHour, 1)
        XCTAssertEqual(pa?.endMinute, 31)
    }

    func test_validTimeRange_nonSleepProblems() {
        let nonSleep: [ProblemType] = [.cantWakeUp, .selfLoathing, .rumination, .procrastination,
                                        .anxiety, .lying, .badMouthing, .alcoholDependency,
                                        .anger, .obsessive, .loneliness]
        for problem in nonSleep {
            let range = problem.validTimeRange
            XCTAssertNotNil(range, "\(problem.rawValue) should have validTimeRange")
            XCTAssertEqual(range?.startHour, 6, "\(problem.rawValue) startHour")
            XCTAssertEqual(range?.endHour, 23, "\(problem.rawValue) endHour")
            XCTAssertEqual(range?.endMinute, 0, "\(problem.rawValue) endMinute")
        }
    }

    func test_isValidTime_crossesMidnight() {
        // staying_up_late: 6:00-01:30 (crosses midnight)
        let sul = ProblemType.stayingUpLate

        // 有効: 6:00, 20:00, 23:00, 0:00, 1:00, 1:29, 1:30
        XCTAssertTrue(sul.isValidTime(hour: 6, minute: 0))
        XCTAssertTrue(sul.isValidTime(hour: 20, minute: 0))
        XCTAssertTrue(sul.isValidTime(hour: 23, minute: 0))
        XCTAssertTrue(sul.isValidTime(hour: 0, minute: 0))
        XCTAssertTrue(sul.isValidTime(hour: 1, minute: 0))
        XCTAssertTrue(sul.isValidTime(hour: 1, minute: 29))
        XCTAssertTrue(sul.isValidTime(hour: 1, minute: 30))

        // 無効: 1:31, 2:00, 3:00, 5:59
        XCTAssertFalse(sul.isValidTime(hour: 1, minute: 31))
        XCTAssertFalse(sul.isValidTime(hour: 2, minute: 0))
        XCTAssertFalse(sul.isValidTime(hour: 3, minute: 0))
        XCTAssertFalse(sul.isValidTime(hour: 5, minute: 59))
    }

    func test_isValidTime_nonSleepProblem() {
        // anxiety: 6:00-23:00
        let anx = ProblemType.anxiety

        // 有効: 6:00, 12:00, 22:59
        XCTAssertTrue(anx.isValidTime(hour: 6, minute: 0))
        XCTAssertTrue(anx.isValidTime(hour: 12, minute: 0))
        XCTAssertTrue(anx.isValidTime(hour: 22, minute: 59))

        // 無効: 23:00, 23:15, 0:00, 5:59
        XCTAssertFalse(anx.isValidTime(hour: 23, minute: 0))
        XCTAssertFalse(anx.isValidTime(hour: 23, minute: 15))
        XCTAssertFalse(anx.isValidTime(hour: 0, minute: 0))
        XCTAssertFalse(anx.isValidTime(hour: 5, minute: 59))
    }

    func test_allSlotsWithinValidTimeRange() {
        // 全スロットが各問題の validTimeRange 内にあることを検証
        for problem in ProblemType.allCases {
            for slot in problem.notificationSchedule {
                XCTAssertTrue(problem.isValidTime(hour: slot.hour, minute: slot.minute),
                    "\(problem.rawValue) slot \(slot.hour):\(String(format: "%02d", slot.minute)) is outside validTimeRange")
            }
        }
    }

    // MARK: - v1.6.0: staying_up_late の新スケジュール（5スロット）

    func test_stayingUpLate_hasCorrectSlots() {
        let slots = ProblemType.stayingUpLate.notificationSchedule
        XCTAssertEqual(slots.count, 5, "staying_up_late should have 5 slots (v1.6.0)")

        let expected = [(20, 0), (22, 0), (23, 30), (0, 0), (1, 0)]
        for (i, exp) in expected.enumerated() {
            XCTAssertEqual(slots[i].hour, exp.0, "Slot \(i+1) hour")
            XCTAssertEqual(slots[i].minute, exp.1, "Slot \(i+1) minute")
        }
    }

    // MARK: - v1.6.0: porn_addiction の新スケジュール（3スロット）

    func test_pornAddiction_hasCorrectSlots() {
        let slots = ProblemType.pornAddiction.notificationSchedule
        XCTAssertEqual(slots.count, 3, "porn_addiction should have 3 slots (v1.6.0)")

        let expected = [(20, 30), (22, 30), (23, 45)]
        for (i, exp) in expected.enumerated() {
            XCTAssertEqual(slots[i].hour, exp.0, "Slot \(i+1) hour")
            XCTAssertEqual(slots[i].minute, exp.1, "Slot \(i+1) minute")
        }
    }

    // MARK: - v1.6.0: 各問題タイプの正確なスロット（3スロット）

    func test_cantWakeUp_hasCorrectSlots() {
        let slots = ProblemType.cantWakeUp.notificationSchedule
        XCTAssertEqual(slots.count, 3)
        let expected = [(6, 0), (6, 45), (7, 15)]
        for (i, exp) in expected.enumerated() {
            XCTAssertEqual(slots[i].hour, exp.0, "cantWakeUp slot \(i+1) hour")
            XCTAssertEqual(slots[i].minute, exp.1, "cantWakeUp slot \(i+1) minute")
        }
    }

    func test_selfLoathing_hasCorrectSlots() {
        let slots = ProblemType.selfLoathing.notificationSchedule
        XCTAssertEqual(slots.count, 3)
        let expected = [(8, 0), (13, 0), (19, 0)]
        for (i, exp) in expected.enumerated() {
            XCTAssertEqual(slots[i].hour, exp.0, "selfLoathing slot \(i+1) hour")
            XCTAssertEqual(slots[i].minute, exp.1, "selfLoathing slot \(i+1) minute")
        }
    }

    func test_obsessive_hasCorrectSlots() {
        let slots = ProblemType.obsessive.notificationSchedule
        XCTAssertEqual(slots.count, 3)
        let expected = [(9, 0), (13, 45), (18, 30)]
        for (i, exp) in expected.enumerated() {
            XCTAssertEqual(slots[i].hour, exp.0, "obsessive slot \(i+1) hour")
            XCTAssertEqual(slots[i].minute, exp.1, "obsessive slot \(i+1) minute")
        }
    }

    // MARK: - P3: notificationVariantCount - v1.8.0: 全問題60バリアントに拡張（20日間新鮮体験）

    func test_variantCount_allProblems() {
        // v1.8.0: notificationVariantCount は全 ProblemType で 60 に統一
        for problem in ProblemType.allCases {
            XCTAssertEqual(problem.notificationVariantCount, 60, "\(problem.rawValue) should have 60 variants")
        }
    }

}
