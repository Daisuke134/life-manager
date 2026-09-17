import Foundation

nonisolated struct TranslationResult: Codable, Identifiable, Sendable {
    let id: UUID
    let originalText: String
    let relationship: RelationshipType
    let honne: String
    let psychologicalState: String
    let suggestedResponse: String
    let emotionLevel: Int
    let timestamp: Date

    init(
        id: UUID = UUID(),
        originalText: String,
        relationship: RelationshipType,
        honne: String,
        psychologicalState: String,
        suggestedResponse: String,
        emotionLevel: Int,
        timestamp: Date = Date()
    ) {
        self.id = id
        self.originalText = originalText
        self.relationship = relationship
        self.honne = honne
        self.psychologicalState = psychologicalState
        self.suggestedResponse = suggestedResponse
        self.emotionLevel = emotionLevel
        self.timestamp = timestamp
    }
}

nonisolated enum RelationshipType: String, Codable, CaseIterable, Sendable {
    case couple = "couple"
    case parentChild = "parent_child"
    case boss = "boss"
    case colleague = "colleague"
    case friend = "friend"

    var displayName: String {
        switch self {
        case .couple: return "夫婦・恋人"
        case .parentChild: return "親子"
        case .boss: return "上司・部下"
        case .colleague: return "同僚"
        case .friend: return "友人"
        }
    }

    var icon: String {
        switch self {
        case .couple: return "heart.fill"
        case .parentChild: return "figure.and.child.holdinghands"
        case .boss: return "person.2.fill"
        case .colleague: return "person.3.fill"
        case .friend: return "face.smiling.fill"
        }
    }
}
