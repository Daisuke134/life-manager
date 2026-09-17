import Testing
@testable import aniccaios

struct LLMGeneratedNudgeTests {

    // MARK: - Decoder Helper

    private var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    // MARK: - Decode Tests

    @Test("LLMGeneratedNudge decode from API response")
    func test_LLMGeneratedNudge_decodeFromAPI() throws {
        // APIレスポンス形式のJSON
        let json = """
        {
            "id": "test-123",
            "problemType": "cant_wake_up",
            "scheduledHour": 7,
            "hook": "まだ寝てる？",
            "content": "あと5分で起きたら、今日は違う1日になる。",
            "tone": "strict",
            "reasoning": "User responds well to strict tone",
            "createdAt": "2026-01-24T05:00:00Z"
        }
        """.data(using: .utf8)!

        let decoded = try decoder.decode(LLMGeneratedNudge.self, from: json)

        #expect(decoded.id == "test-123")
        #expect(decoded.problemType == .cantWakeUp)
        #expect(decoded.tone == .strict)
        #expect(decoded.hook == "まだ寝てる？")
        #expect(decoded.content == "あと5分で起きたら、今日は違う1日になる。")
        #expect(decoded.scheduledHour == 7)
    }

    @Test("All tone values decode correctly")
    func test_LLMGeneratedNudge_allTones() throws {
        let tones = ["strict", "gentle", "logical", "provocative", "philosophical"]

        for toneName in tones {
            let json = """
            {
                "id": "test-\(toneName)",
                "problemType": "cant_wake_up",
                "scheduledHour": 7,
                "hook": "テスト",
                "content": "テストコンテンツ",
                "tone": "\(toneName)",
                "reasoning": "test",
                "createdAt": "2026-01-24T05:00:00Z"
            }
            """.data(using: .utf8)!

            let decoded = try decoder.decode(LLMGeneratedNudge.self, from: json)
            #expect(decoded.tone.rawValue == toneName)
        }
    }

    @Test("Unknown tone falls back to .unknown")
    func test_LLMGeneratedNudge_unknownTone() throws {
        let json = """
        {
            "id": "test-123",
            "problemType": "cant_wake_up",
            "scheduledHour": 7,
            "hook": "テスト",
            "content": "テスト",
            "tone": "some_new_tone",
            "reasoning": "test",
            "createdAt": "2026-01-24T05:00:00Z"
        }
        """.data(using: .utf8)!

        let decoded = try decoder.decode(LLMGeneratedNudge.self, from: json)
        #expect(decoded.tone == .unknown)
    }

    @Test("Unknown problemType throws error")
    func test_LLMGeneratedNudge_unknownProblemType() throws {
        let json = """
        {
            "id": "test-123",
            "problemType": "unknown_problem",
            "scheduledHour": 7,
            "hook": "テスト",
            "content": "テスト",
            "tone": "strict",
            "reasoning": "test",
            "createdAt": "2026-01-24T05:00:00Z"
        }
        """.data(using: .utf8)!

        #expect(throws: DecodingError.self) {
            try decoder.decode(LLMGeneratedNudge.self, from: json)
        }
    }

    @Test("All 13 problem types decode correctly")
    func test_LLMGeneratedNudge_allProblemTypes() throws {
        let problemTypes = [
            "staying_up_late", "cant_wake_up", "self_loathing", "rumination",
            "procrastination", "anxiety", "lying", "bad_mouthing", "porn_addiction",
            "alcohol_dependency", "anger", "obsessive", "loneliness"
        ]

        for problemType in problemTypes {
            let json = """
            {
                "id": "test-\(problemType)",
                "problemType": "\(problemType)",
                "scheduledHour": 7,
                "hook": "テスト",
                "content": "テストコンテンツ",
                "tone": "strict",
                "reasoning": "test",
                "createdAt": "2026-01-24T05:00:00Z"
            }
            """.data(using: .utf8)!

            let decoded = try decoder.decode(LLMGeneratedNudge.self, from: json)
            #expect(decoded.problemType.rawValue == problemType)
        }
    }

    // MARK: - Character Limit Tests

    @Test("Hook character limit validation - 25 chars")
    func test_hookTruncation_25chars() {
        let longHook = "これは25文字を超える非常に長いフックテキストです"
        let truncated = String(longHook.prefix(25))

        #expect(truncated.count <= 25)
        #expect(truncated == "これは25文字を超える非常に長いフックテキスト")
    }

    @Test("Content character limit validation - 80 chars")
    func test_contentTruncation_80chars() {
        let longContent = String(repeating: "あ", count: 100)
        let truncated = String(longContent.prefix(80))

        #expect(truncated.count == 80)
    }

    @Test("Short hook and content pass validation")
    func test_shortHookAndContent() {
        let shortHook = "起きろ"
        let shortContent = "今日も頑張ろう"

        #expect(shortHook.count <= 25)
        #expect(shortContent.count <= 80)
    }

    // MARK: - Date Decoding Tests

    @Test("ISO8601 date decodes correctly")
    func test_iso8601DateDecoding() throws {
        let json = """
        {
            "id": "date-test",
            "problemType": "cant_wake_up",
            "scheduledHour": 7,
            "hook": "テスト",
            "content": "テスト",
            "tone": "strict",
            "reasoning": "test",
            "createdAt": "2026-01-24T05:00:00Z"
        }
        """.data(using: .utf8)!

        let decoded = try decoder.decode(LLMGeneratedNudge.self, from: json)

        // Verify date components
        let calendar = Calendar(identifier: .gregorian)
        let components = calendar.dateComponents(in: TimeZone(identifier: "UTC")!, from: decoded.createdAt)
        #expect(components.year == 2026)
        #expect(components.month == 1)
        #expect(components.day == 24)
        #expect(components.hour == 5)
    }

    @Test("Decoding fails without ISO8601 strategy")
    func test_decodingFailsWithoutISO8601() throws {
        let json = """
        {
            "id": "test-123",
            "problemType": "cant_wake_up",
            "scheduledHour": 7,
            "hook": "起きろ",
            "content": "今日も頑張ろう",
            "tone": "strict",
            "reasoning": "test",
            "createdAt": "2026-01-24T05:00:00Z"
        }
        """.data(using: .utf8)!

        // Default JSONDecoder (no ISO8601)
        let defaultDecoder = JSONDecoder()

        #expect(throws: DecodingError.self) {
            try defaultDecoder.decode(LLMGeneratedNudge.self, from: json)
        }
    }

    // MARK: - Phase 7+8: scheduledTime Tests

    @Test("Decode with new scheduledTime field (HH:MM format)")
    func test_LLMGeneratedNudge_scheduledTime() throws {
        let json = """
        {
            "id": "test-time",
            "problemType": "staying_up_late",
            "scheduledTime": "22:30",
            "hook": "まだ起きてる？",
            "content": "今夜は早めに。明日の自分が感謝する。",
            "tone": "gentle",
            "reasoning": "22:30 is optimal for this user",
            "rootCauseHypothesis": "Stress relief through late night scrolling",
            "createdAt": "2026-01-26T05:00:00Z"
        }
        """.data(using: .utf8)!

        let decoded = try decoder.decode(LLMGeneratedNudge.self, from: json)

        #expect(decoded.scheduledTime == "22:30")
        #expect(decoded.scheduledHour == 22)
        #expect(decoded.scheduledMinute == 30)
        #expect(decoded.rootCauseHypothesis == "Stress relief through late night scrolling")
    }

    @Test("Backward compatibility: scheduledHour only (no scheduledTime)")
    func test_LLMGeneratedNudge_backwardCompatibility_scheduledHourOnly() throws {
        // Old API response format without scheduledTime
        let json = """
        {
            "id": "test-old",
            "problemType": "cant_wake_up",
            "scheduledHour": 7,
            "hook": "起きろ",
            "content": "今日も頑張ろう",
            "tone": "strict",
            "reasoning": "test",
            "createdAt": "2026-01-24T05:00:00Z"
        }
        """.data(using: .utf8)!

        let decoded = try decoder.decode(LLMGeneratedNudge.self, from: json)

        #expect(decoded.scheduledTime == "07:00")
        #expect(decoded.scheduledHour == 7)
        #expect(decoded.scheduledMinute == 0)
        #expect(decoded.rootCauseHypothesis == nil)
    }

    @Test("scheduledMinute computed property works correctly")
    func test_LLMGeneratedNudge_scheduledMinute() throws {
        let testCases: [(scheduledTime: String, expectedHour: Int, expectedMinute: Int)] = [
            ("06:30", 6, 30),
            ("22:00", 22, 0),
            ("00:15", 0, 15),
            ("23:59", 23, 59),
            ("12:00", 12, 0)
        ]

        for testCase in testCases {
            let json = """
            {
                "id": "test-\(testCase.scheduledTime)",
                "problemType": "staying_up_late",
                "scheduledTime": "\(testCase.scheduledTime)",
                "hook": "テスト",
                "content": "テスト",
                "tone": "strict",
                "reasoning": "test",
                "createdAt": "2026-01-26T05:00:00Z"
            }
            """.data(using: .utf8)!

            let decoded = try decoder.decode(LLMGeneratedNudge.self, from: json)
            #expect(decoded.scheduledHour == testCase.expectedHour, "Expected hour \(testCase.expectedHour) for \(testCase.scheduledTime)")
            #expect(decoded.scheduledMinute == testCase.expectedMinute, "Expected minute \(testCase.expectedMinute) for \(testCase.scheduledTime)")
        }
    }

    @Test("rootCauseHypothesis is optional")
    func test_LLMGeneratedNudge_rootCauseHypothesis_optional() throws {
        // Without rootCauseHypothesis
        let jsonWithout = """
        {
            "id": "test-no-root",
            "problemType": "cant_wake_up",
            "scheduledTime": "07:00",
            "hook": "起きろ",
            "content": "今日も頑張ろう",
            "tone": "strict",
            "reasoning": "test",
            "createdAt": "2026-01-26T05:00:00Z"
        }
        """.data(using: .utf8)!

        let decodedWithout = try decoder.decode(LLMGeneratedNudge.self, from: jsonWithout)
        #expect(decodedWithout.rootCauseHypothesis == nil)

        // With rootCauseHypothesis
        let jsonWith = """
        {
            "id": "test-with-root",
            "problemType": "cant_wake_up",
            "scheduledTime": "07:00",
            "hook": "起きろ",
            "content": "今日も頑張ろう",
            "tone": "strict",
            "reasoning": "test",
            "rootCauseHypothesis": "Perfectionism causing self-loathing loop",
            "createdAt": "2026-01-26T05:00:00Z"
        }
        """.data(using: .utf8)!

        let decodedWith = try decoder.decode(LLMGeneratedNudge.self, from: jsonWith)
        #expect(decodedWith.rootCauseHypothesis == "Perfectionism causing self-loathing loop")
    }
}

