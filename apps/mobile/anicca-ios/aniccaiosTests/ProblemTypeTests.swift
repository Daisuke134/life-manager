import Testing
@testable import aniccaios

struct ProblemTypeTests {

    // MARK: - v1.6.0: スロット数リデザイン（3回/日、夜更かしのみ5回）

    @Test("staying_up_late has 5 slots (exception)")
    func test_stayingUpLate_has5Slots() {
        #expect(
            ProblemType.stayingUpLate.notificationSchedule.count == 5,
            "staying_up_late should have 5 slots (night intervention exception)"
        )
    }

    @Test("All other problem types have 3 slots")
    func test_otherProblemTypes_have3Slots() {
        let exceptions: Set<ProblemType> = [.stayingUpLate]
        for problem in ProblemType.allCases where !exceptions.contains(problem) {
            #expect(
                problem.notificationSchedule.count == 3,
                "\(problem.rawValue) has \(problem.notificationSchedule.count) slots, expected 3"
            )
        }
    }

    // MARK: - v1.6.0: 各問題のスロットが正しいか

    @Test("staying_up_late slots match v1.6.0 redesign")
    func test_stayingUpLate_slotsMatchRedesign() {
        let slots = ProblemType.stayingUpLate.notificationSchedule
        let expected: [(Int, Int)] = [(20, 0), (22, 0), (23, 30), (0, 0), (1, 0)]
        #expect(slots.count == expected.count)
        for (i, slot) in slots.enumerated() {
            #expect(slot.hour == expected[i].0, "Slot \(i) hour mismatch")
            #expect(slot.minute == expected[i].1, "Slot \(i) minute mismatch")
        }
    }

    @Test("cant_wake_up has correct wake window slots")
    func test_cantWakeUp_slotsMatchRedesign() {
        let slots = ProblemType.cantWakeUp.notificationSchedule
        let expected: [(Int, Int)] = [(6, 0), (6, 45), (7, 15)]
        #expect(slots.count == expected.count)
        for (i, slot) in slots.enumerated() {
            #expect(slot.hour == expected[i].0, "Slot \(i) hour mismatch")
            #expect(slot.minute == expected[i].1, "Slot \(i) minute mismatch")
        }
    }

    @Test("rumination slots match v1.6.0 redesign")
    func test_rumination_slotsMatchRedesign() {
        let slots = ProblemType.rumination.notificationSchedule
        let expected: [(Int, Int)] = [(8, 30), (14, 0), (21, 0)]
        #expect(slots.count == expected.count)
        for (i, slot) in slots.enumerated() {
            #expect(slot.hour == expected[i].0, "Slot \(i) hour mismatch")
            #expect(slot.minute == expected[i].1, "Slot \(i) minute mismatch")
        }
    }

    // MARK: - v1.6.0: 最低15分間隔を保証

    @Test("All slots have at least 15 minutes interval")
    func test_allSlots_have15MinInterval() {
        // 全問題選択時のスロットをソートして間隔を検証
        var allSlots: [(problem: ProblemType, hour: Int, minute: Int)] = []
        for problem in ProblemType.allCases {
            for slot in problem.notificationSchedule {
                allSlots.append((problem, slot.hour, slot.minute))
            }
        }

        // 時刻でソート（深夜0-5時は+24hで翌日扱い）
        allSlots.sort { a, b in
            let aKey = (a.hour < 6 ? a.hour + 24 : a.hour) * 60 + a.minute
            let bKey = (b.hour < 6 ? b.hour + 24 : b.hour) * 60 + b.minute
            return aKey < bKey
        }

        // 隣接スロット間の間隔が15分以上か確認
        for i in 1..<allSlots.count {
            let prev = allSlots[i - 1]
            let curr = allSlots[i]
            let prevMinutes = (prev.hour < 6 ? prev.hour + 24 : prev.hour) * 60 + prev.minute
            let currMinutes = (curr.hour < 6 ? curr.hour + 24 : curr.hour) * 60 + curr.minute
            let interval = currMinutes - prevMinutes
            #expect(
                interval >= 15,
                "Interval between \(prev.problem.rawValue)@\(prev.hour):\(prev.minute) and \(curr.problem.rawValue)@\(curr.hour):\(curr.minute) is \(interval) min, expected >= 15"
            )
        }
    }
}
