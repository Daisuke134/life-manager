import Foundation

/// カスタム課題（ユーザー定義）
struct CustomProblem: Codable, Identifiable, Equatable {
    let id: UUID
    let name: String
    let createdAt: Date
    var problemDetails: [String: [String]]?  // 深掘り回答（問題ID: 選択した選択肢）

    init(id: UUID = UUID(), name: String, createdAt: Date = Date(), problemDetails: [String: [String]]? = nil) {
        self.id = id
        self.name = name
        self.createdAt = createdAt
        self.problemDetails = problemDetails
    }
}

