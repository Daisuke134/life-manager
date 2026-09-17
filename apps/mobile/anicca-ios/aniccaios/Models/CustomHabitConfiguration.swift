import Foundation

struct CustomHabitConfiguration: Codable, Equatable, Identifiable {
    let id: UUID
    let name: String
    let updatedAt: Date
    
    init(id: UUID = UUID(), name: String, updatedAt: Date = Date()) {
        self.id = id
        self.name = name
        self.updatedAt = updatedAt
    }
}

final class CustomHabitStore {
    static let shared = CustomHabitStore()
    
    private let defaults = UserDefaults.standard
    private let storageKey = "com.anicca.customHabits" // 変更: 複数形に
    
    private init() {}
    
    // 変更: 配列対応
    func loadAll() -> [CustomHabitConfiguration] {
        guard let data = defaults.data(forKey: storageKey) else {
            // マイグレーション: 旧形式のデータを読み込む
            return migrateLegacyHabit()
        }
        guard let habits = try? JSONDecoder().decode([CustomHabitConfiguration].self, from: data) else {
            return []
        }
        return habits
    }
    
    func saveAll(_ configurations: [CustomHabitConfiguration]) {
        if let data = try? JSONEncoder().encode(configurations) {
            defaults.set(data, forKey: storageKey)
        } else {
            defaults.removeObject(forKey: storageKey)
        }
        // UserDefaults.synchronize() は削除（iOSでは自動同期されるため非推奨）
    }
    
    func add(_ configuration: CustomHabitConfiguration) {
        var habits = loadAll()
        let name = configuration.name.trimmingCharacters(in: .whitespacesAndNewlines)
        if habits.contains(where: { $0.name.compare(name, options: .caseInsensitive) == .orderedSame }) { return }
        habits.append(configuration)
        saveAll(habits)
    }
    
    func remove(at index: Int) {
        var habits = loadAll()
        guard index >= 0 && index < habits.count else { return }
        habits.remove(at: index)
        saveAll(habits)
    }
    
    func remove(id: UUID) {
        var habits = loadAll()
        habits.removeAll { $0.id == id }
        saveAll(habits)
    }
    
    func update(at index: Int, configuration: CustomHabitConfiguration) {
        var habits = loadAll()
        guard index >= 0 && index < habits.count else { return }
        habits[index] = configuration
        saveAll(habits)
    }
    
    // マイグレーション: 旧形式の単一カスタム習慣を配列に変換
    private func migrateLegacyHabit() -> [CustomHabitConfiguration] {
        let legacyKey = "com.anicca.customHabit"
        guard let data = defaults.data(forKey: legacyKey),
              let oldConfig = try? JSONDecoder().decode(CustomHabitConfiguration.self, from: data) else {
            return []
        }
        // 旧データを新形式に変換
        let migrated = CustomHabitConfiguration(id: UUID(), name: oldConfig.name, updatedAt: oldConfig.updatedAt)
        defaults.removeObject(forKey: legacyKey)
        saveAll([migrated])
        return [migrated]
    }
    
    // 後方互換性のため残す
    func load() -> CustomHabitConfiguration? {
        return loadAll().first
    }
    
    func save(_ configuration: CustomHabitConfiguration?) {
        if let config = configuration {
            saveAll([config])
        } else {
            saveAll([])
        }
    }
    
    func displayName(fallback: String) -> String {
        guard let name = loadAll().first?.name, !name.isEmpty else {
            return fallback
        }
        return name
    }
}


