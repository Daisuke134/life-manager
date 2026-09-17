import Foundation
import Combine

/// ユーザーが各問題について Anicca に伝えたいこと
struct Memory: Codable, Identifiable {
    let id: UUID
    let problemType: String
    let text: String
    let createdAt: Date
    let updatedAt: Date

    init(problemType: ProblemType, text: String) {
        self.id = UUID()
        self.problemType = problemType.rawValue
        self.text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}

// MARK: - MemoryStore
final class MemoryStore: ObservableObject {
    static let shared = MemoryStore()

    @Published private(set) var memories: [String: Memory] = [:]  // problemType -> Memory

    private let userDefaultsKey = "anicca_memories"

    private init() {
        loadFromStorage()
    }

    /// メモリを保存（空文字は保存しない）
    func save(text: String, for problem: ProblemType) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            // 空文字の場合は削除
            memories.removeValue(forKey: problem.rawValue)
            saveToStorage()
            return
        }

        let memory = Memory(problemType: problem, text: trimmed)
        memories[problem.rawValue] = memory
        saveToStorage()
    }

    /// 特定の問題のメモリを取得
    func memory(for problem: ProblemType) -> Memory? {
        return memories[problem.rawValue]
    }

    /// 特定の問題のメモリを削除
    func delete(for problem: ProblemType) {
        memories.removeValue(forKey: problem.rawValue)
        saveToStorage()
    }

    private func saveToStorage() {
        if let encoded = try? JSONEncoder().encode(Array(memories.values)) {
            UserDefaults.standard.set(encoded, forKey: userDefaultsKey)
        }
    }

    private func loadFromStorage() {
        guard let data = UserDefaults.standard.data(forKey: userDefaultsKey),
              let decoded = try? JSONDecoder().decode([Memory].self, from: data) else {
            return
        }
        memories = Dictionary(uniqueKeysWithValues: decoded.map { ($0.problemType, $0) })
    }
}



