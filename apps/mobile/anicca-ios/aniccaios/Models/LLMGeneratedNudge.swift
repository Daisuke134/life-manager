import Foundation

/// LLM生成Nudgeのトーン
enum NudgeTone: String, Codable, CaseIterable {
    case strict
    case gentle
    case logical
    case provocative
    case philosophical
    case unknown  // 未知値のフォールバック

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        let rawValue = try container.decode(String.self)
        self = NudgeTone(rawValue: rawValue) ?? .unknown
    }
}

/// LLM生成されたNudgeコンテンツ
struct LLMGeneratedNudge: Codable {
    let id: String
    let problemType: ProblemType
    let scheduledTime: String          // "HH:MM" format (Phase 7+8)
    let hook: String                   // 通知テキスト（25文字以内）
    let content: String                // OneScreenテキスト（80文字以内）
    let tone: NudgeTone
    let reasoning: String              // LLMの判断理由
    let rootCauseHypothesis: String?   // Phase 7+8: 根本原因の推測
    let createdAt: Date

    // MARK: - Computed Properties (後方互換)

    /// scheduledTimeから時間を取得（後方互換）
    var scheduledHour: Int {
        let components = scheduledTime.split(separator: ":")
        return Int(components.first ?? "0") ?? 0
    }

    /// scheduledTimeから分を取得
    var scheduledMinute: Int {
        let components = scheduledTime.split(separator: ":")
        guard components.count > 1 else { return 0 }
        return Int(components[1]) ?? 0
    }

    enum CodingKeys: String, CodingKey {
        case id, problemType, scheduledTime, scheduledHour, hook, content, tone
        case reasoning, rootCauseHypothesis, createdAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)

        // problemTypeはAPIが文字列で返すので、ProblemType enumに変換
        let problemTypeString = try container.decode(String.self, forKey: .problemType)
        guard let problemType = ProblemType(rawValue: problemTypeString) else {
            throw DecodingError.dataCorruptedError(
                forKey: .problemType,
                in: container,
                debugDescription: "Unknown problemType: \(problemTypeString)"
            )
        }
        self.problemType = problemType

        // scheduledTime があれば使う、なければ scheduledHour から計算（後方互換）
        if let time = try? container.decode(String.self, forKey: .scheduledTime) {
            scheduledTime = time
        } else {
            let hour = try container.decode(Int.self, forKey: .scheduledHour)
            scheduledTime = String(format: "%02d:00", hour)
        }

        hook = try container.decode(String.self, forKey: .hook)
        content = try container.decode(String.self, forKey: .content)
        tone = try container.decode(NudgeTone.self, forKey: .tone)
        reasoning = try container.decode(String.self, forKey: .reasoning)
        rootCauseHypothesis = try? container.decode(String.self, forKey: .rootCauseHypothesis)
        createdAt = try container.decode(Date.self, forKey: .createdAt)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(problemType.rawValue, forKey: .problemType)
        try container.encode(scheduledTime, forKey: .scheduledTime)
        try container.encode(scheduledHour, forKey: .scheduledHour)  // 後方互換のため両方出力
        try container.encode(hook, forKey: .hook)
        try container.encode(content, forKey: .content)
        try container.encode(tone, forKey: .tone)
        try container.encode(reasoning, forKey: .reasoning)
        try container.encodeIfPresent(rootCauseHypothesis, forKey: .rootCauseHypothesis)
        try container.encode(createdAt, forKey: .createdAt)
    }

    // MARK: - Test Helper (internal)

    #if DEBUG
    /// テスト用イニシャライザ
    init(
        id: String,
        problemType: ProblemType,
        scheduledTime: String,
        hook: String,
        content: String,
        tone: NudgeTone = .strict,
        reasoning: String = "test",
        rootCauseHypothesis: String? = nil,
        createdAt: Date = Date()
    ) {
        self.id = id
        self.problemType = problemType
        self.scheduledTime = scheduledTime
        self.hook = hook
        self.content = content
        self.tone = tone
        self.reasoning = reasoning
        self.rootCauseHypothesis = rootCauseHypothesis
        self.createdAt = createdAt
    }
    #endif
}
