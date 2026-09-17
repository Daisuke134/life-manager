import Foundation

extension Array {
    /// IndexSetで指定された要素を新しい位置に移動する
    /// SwiftUIの`.onMove`モディファイアで使用するためのメソッド
    mutating func move(fromOffsets source: IndexSet, toOffset destination: Int) {
        guard !source.isEmpty else { return }
        
        // destinationを有効な範囲に制限
        let validDestination = Swift.max(0, Swift.min(destination, self.count))
        
        let itemsToMove = source.map { self[$0] }
        var adjustedDestination = validDestination
        
        // 後ろから削除することで、インデックスのずれを防ぐ
        for sourceIndex in source.sorted(by: >) {
            self.remove(at: sourceIndex)
            if sourceIndex < validDestination {
                adjustedDestination -= 1
            }
        }
        
        // 新しい位置に挿入
        for (index, item) in itemsToMove.enumerated() {
            self.insert(item, at: adjustedDestination + index)
        }
    }
}

