import Testing
@testable import aniccaios

@MainActor
struct LLMNudgeCacheTests {

    // MARK: - Test Helpers

    private var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    /// テスト用ヘルパー: LLMGeneratedNudgeを作成（JSONデコード経由）
    private func makeTestNudge(
        id: String = "test-123",
        problemType: ProblemType = .cantWakeUp,
        scheduledHour: Int = 7,
        hook: String = "起きろ",
        content: String = "今日も頑張ろう"
    ) throws -> LLMGeneratedNudge {
        let json = """
        {
            "id": "\(id)",
            "problemType": "\(problemType.rawValue)",
            "scheduledHour": \(scheduledHour),
            "hook": "\(hook)",
            "content": "\(content)",
            "tone": "strict",
            "reasoning": "test",
            "createdAt": "2026-01-24T05:00:00Z"
        }
        """.data(using: .utf8)!
        return try decoder.decode(LLMGeneratedNudge.self, from: json)
    }

    // MARK: - Basic Cache Tests

    @Test("Set and get nudge from cache")
    func test_LLMNudgeCache_setAndGet() async throws {
        let cache = LLMNudgeCache.shared
        cache.clear()

        let nudge = try makeTestNudge()
        cache.setNudges([nudge])

        let retrieved = cache.getNudge(for: .cantWakeUp, hour: 7)
        #expect(retrieved != nil)
        #expect(retrieved?.id == "test-123")
        #expect(retrieved?.problemType == .cantWakeUp)
        #expect(retrieved?.scheduledHour == 7)
    }

    @Test("Return nil for missing nudge")
    func test_LLMNudgeCache_missingNudge() async {
        let cache = LLMNudgeCache.shared
        cache.clear()

        let retrieved = cache.getNudge(for: .cantWakeUp, hour: 7)
        #expect(retrieved == nil)
    }

    @Test("Clear removes all nudges")
    func test_LLMNudgeCache_clear() async throws {
        let cache = LLMNudgeCache.shared
        cache.clear()

        // Add nudges
        let nudge1 = try makeTestNudge(id: "nudge-1", problemType: .cantWakeUp, scheduledHour: 7)
        let nudge2 = try makeTestNudge(id: "nudge-2", problemType: .stayingUpLate, scheduledHour: 23)
        cache.setNudges([nudge1, nudge2])

        // Verify they exist
        #expect(cache.getNudge(for: .cantWakeUp, hour: 7) != nil)
        #expect(cache.getNudge(for: .stayingUpLate, hour: 23) != nil)

        // Clear and verify
        cache.clear()
        #expect(cache.getNudge(for: .cantWakeUp, hour: 7) == nil)
        #expect(cache.getNudge(for: .stayingUpLate, hour: 23) == nil)
    }

    // MARK: - Multiple Nudge Tests

    @Test("Store multiple nudges for different problems")
    func test_LLMNudgeCache_multipleProblems() async throws {
        let cache = LLMNudgeCache.shared
        cache.clear()

        let nudge1 = try makeTestNudge(id: "wake-up", problemType: .cantWakeUp, scheduledHour: 7)
        let nudge2 = try makeTestNudge(id: "stay-up", problemType: .stayingUpLate, scheduledHour: 23)
        let nudge3 = try makeTestNudge(id: "anxiety", problemType: .anxiety, scheduledHour: 14)

        cache.setNudges([nudge1, nudge2, nudge3])

        #expect(cache.getNudge(for: .cantWakeUp, hour: 7)?.id == "wake-up")
        #expect(cache.getNudge(for: .stayingUpLate, hour: 23)?.id == "stay-up")
        #expect(cache.getNudge(for: .anxiety, hour: 14)?.id == "anxiety")
    }

    @Test("Store multiple nudges for same problem at different hours")
    func test_LLMNudgeCache_sameProbleDifferentHours() async throws {
        let cache = LLMNudgeCache.shared
        cache.clear()

        let nudge1 = try makeTestNudge(id: "wake-7", problemType: .cantWakeUp, scheduledHour: 7)
        let nudge2 = try makeTestNudge(id: "wake-8", problemType: .cantWakeUp, scheduledHour: 8)

        cache.setNudges([nudge1, nudge2])

        #expect(cache.getNudge(for: .cantWakeUp, hour: 7)?.id == "wake-7")
        #expect(cache.getNudge(for: .cantWakeUp, hour: 8)?.id == "wake-8")
        #expect(cache.getNudge(for: .cantWakeUp, hour: 9) == nil)
    }

    @Test("Overwrite existing nudge with same key")
    func test_LLMNudgeCache_overwrite() async throws {
        let cache = LLMNudgeCache.shared
        cache.clear()

        let nudge1 = try makeTestNudge(id: "original", problemType: .cantWakeUp, scheduledHour: 7)
        cache.setNudges([nudge1])
        #expect(cache.getNudge(for: .cantWakeUp, hour: 7)?.id == "original")

        let nudge2 = try makeTestNudge(id: "updated", problemType: .cantWakeUp, scheduledHour: 7)
        cache.setNudges([nudge2])
        #expect(cache.getNudge(for: .cantWakeUp, hour: 7)?.id == "updated")
    }

    // MARK: - Edge Cases

    @Test("Handle edge hour values")
    func test_LLMNudgeCache_edgeHours() async throws {
        let cache = LLMNudgeCache.shared
        cache.clear()

        let nudge0 = try makeTestNudge(id: "hour-0", problemType: .stayingUpLate, scheduledHour: 0)
        let nudge23 = try makeTestNudge(id: "hour-23", problemType: .stayingUpLate, scheduledHour: 23)

        cache.setNudges([nudge0, nudge23])

        #expect(cache.getNudge(for: .stayingUpLate, hour: 0)?.id == "hour-0")
        #expect(cache.getNudge(for: .stayingUpLate, hour: 23)?.id == "hour-23")
    }

    @Test("Empty nudges array does not crash")
    func test_LLMNudgeCache_emptyArray() async {
        let cache = LLMNudgeCache.shared
        cache.clear()

        cache.setNudges([])
        #expect(cache.getNudge(for: .cantWakeUp, hour: 7) == nil)
    }

    // MARK: - Phase 7+8: 30-minute Window Matching Tests

    @Test("Match nudge within 30-minute window")
    func test_getNudge_matches_30min_window() async throws {
        let cache = LLMNudgeCache.shared
        cache.clear()

        // scheduledTime: 22:30 のNudgeを登録
        let nudge = try makeTestNudge(
            id: "test-2230",
            problemType: .stayingUpLate,
            scheduledHour: 22,  // 後方互換のためscheduledHourで作成
            hook: "まだ起きてる？"
        )
        cache.setNudges([nudge])

        // 正確な時刻でマッチ
        #expect(cache.getNudge(for: .stayingUpLate, hour: 22)?.id == "test-2230")

        // 30分以内でマッチ（22:15 → 22:00 のNudgeにマッチするべき）
        // 注: 現在のテストは scheduledHour ベースなので、後で minute を追加する
    }

    @Test("Key collision prevention - same hour different minutes")
    func test_keyCollision_prevention() async {
        let cache = LLMNudgeCache.shared
        cache.clear()

        // 同じ時間帯だが分が異なる2つのNudge（22:00と22:30）
        // DEBUG ビルドでのみテスト用イニシャライザを使用
        let nudge1 = LLMGeneratedNudge(
            id: "nudge-2200",
            problemType: .stayingUpLate,
            scheduledTime: "22:00",
            hook: "22:00のNudge",
            content: "Content for 22:00"
        )
        let nudge2 = LLMGeneratedNudge(
            id: "nudge-2230",
            problemType: .stayingUpLate,
            scheduledTime: "22:30",
            hook: "22:30のNudge",
            content: "Content for 22:30"
        )

        cache.setNudges([nudge1, nudge2])

        // 両方のNudgeが取得できる（キー衝突していない）
        #expect(cache.getNudge(for: .stayingUpLate, hour: 22, minute: 0)?.id == "nudge-2200")
        #expect(cache.getNudge(for: .stayingUpLate, hour: 22, minute: 30)?.id == "nudge-2230")
    }

    @Test("30-minute fuzzy matching works correctly")
    func test_fuzzy_matching_30min() async {
        let cache = LLMNudgeCache.shared
        cache.clear()

        let nudge = LLMGeneratedNudge(
            id: "nudge-0630",
            problemType: .cantWakeUp,
            scheduledTime: "06:30",
            hook: "起きろ",
            content: "今日も頑張ろう"
        )
        cache.setNudges([nudge])

        // 完全一致
        #expect(cache.getNudge(for: .cantWakeUp, hour: 6, minute: 30)?.id == "nudge-0630")

        // 30分以内でマッチ
        #expect(cache.getNudge(for: .cantWakeUp, hour: 6, minute: 45)?.id == "nudge-0630")
        #expect(cache.getNudge(for: .cantWakeUp, hour: 6, minute: 15)?.id == "nudge-0630")
        #expect(cache.getNudge(for: .cantWakeUp, hour: 7, minute: 0)?.id == "nudge-0630")

        // 30分超過でマッチしない
        #expect(cache.getNudge(for: .cantWakeUp, hour: 7, minute: 30) == nil)
        #expect(cache.getNudge(for: .cantWakeUp, hour: 5, minute: 30) == nil)
    }

    // MARK: - v1.5.0: hasNudge Tests

    @Test("hasNudge returns true when nudge exists")
    func test_hasNudge_returnsTrue() async throws {
        let cache = LLMNudgeCache.shared
        cache.clear()

        let nudge = try makeTestNudge()
        cache.setNudges([nudge])

        #expect(cache.hasNudge(for: .cantWakeUp, hour: 7) == true)
    }

    @Test("hasNudge returns false when nudge does not exist")
    func test_hasNudge_returnsFalse() async {
        let cache = LLMNudgeCache.shared
        cache.clear()

        #expect(cache.hasNudge(for: .cantWakeUp, hour: 7) == false)
    }

    @Test("hasNudge returns false for wrong problem type")
    func test_hasNudge_wrongProblem() async throws {
        let cache = LLMNudgeCache.shared
        cache.clear()

        let nudge = try makeTestNudge(problemType: .cantWakeUp, scheduledHour: 7)
        cache.setNudges([nudge])

        #expect(cache.hasNudge(for: .stayingUpLate, hour: 7) == false)
    }

    @Test("Multiple nudges with different minutes are stored correctly")
    func test_multipleNudges_differentMinutes() async {
        let cache = LLMNudgeCache.shared
        cache.clear()

        let nudges = [
            LLMGeneratedNudge(id: "n1", problemType: .stayingUpLate, scheduledTime: "21:00", hook: "h1", content: "c1"),
            LLMGeneratedNudge(id: "n2", problemType: .stayingUpLate, scheduledTime: "22:30", hook: "h2", content: "c2"),
            LLMGeneratedNudge(id: "n3", problemType: .stayingUpLate, scheduledTime: "00:00", hook: "h3", content: "c3")
        ]
        cache.setNudges(nudges)

        // 各Nudgeが正しく取得できる
        #expect(cache.getNudge(for: .stayingUpLate, hour: 21, minute: 0)?.id == "n1")
        #expect(cache.getNudge(for: .stayingUpLate, hour: 22, minute: 30)?.id == "n2")
        #expect(cache.getNudge(for: .stayingUpLate, hour: 0, minute: 0)?.id == "n3")
    }
}

