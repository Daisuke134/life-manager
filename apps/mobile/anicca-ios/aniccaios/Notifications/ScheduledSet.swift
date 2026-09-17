import Foundation

/// Represents a scheduled alarm set for comparison
struct ScheduledSet: Equatable {
    let hour: Int
    let minute: Int
    let followup: Int
    let ids: [UUID]
}








