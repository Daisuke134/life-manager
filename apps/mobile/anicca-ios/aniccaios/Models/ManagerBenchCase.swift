import Foundation

/// A complete assignment and its measured responses. No message text or raw profile enters this row.
struct ManagerBenchCase: Codable, Equatable {
    var schemaVersion = 1
    var personId: String
    var deliveryId: String
    var decisionPointAt: Date
    var source: String
    var outcomeWindowSec: Int
    var situation: Situation
    var stimulus: Stimulus
    var response = Response()
    var observationWindowClosedAt: Date?

    struct Situation: Codable, Equatable {
        var answerSnapshot: [String: [String]]
        var answerVersion: Int
        var scheduledTimeBand: String
        var weekday: String
        var notificationPermission: String
        var notificationPermissionObservedAt: Date? = nil
    }

    struct Stimulus: Codable, Equatable {
        var messageId: String
        var category: String
        var tags: [String]
        var scheduledAt: Date?
        var deliveredAt: Date?
        var treatmentAssigned: String
        var assignedProbability: Double
        var policyVersion: String

        private enum CodingKeys: String, CodingKey {
            case messageId, category, tags, scheduledAt, deliveredAt
            case treatmentAssigned, assignedProbability, policyVersion
        }

        func encode(to encoder: Encoder) throws {
            var container = encoder.container(keyedBy: CodingKeys.self)
            try container.encode(messageId, forKey: .messageId)
            try container.encode(category, forKey: .category)
            try container.encode(tags, forKey: .tags)
            try container.encode(scheduledAt, forKey: .scheduledAt)
            try container.encode(deliveredAt, forKey: .deliveredAt)
            try container.encode(treatmentAssigned, forKey: .treatmentAssigned)
            try container.encode(assignedProbability, forKey: .assignedProbability)
            try container.encode(policyVersion, forKey: .policyVersion)
        }
    }

    struct Response: Codable, Equatable {
        var notificationDelivered: Bool?
        var notificationDeliveredAt: Date?
        var notificationOpened: Bool?
        var notificationOpenedAt: Date?
        var appOpened: Bool?
        var appOpenedAt: Date?
        var responded: Bool?
        var respondedAt: Date?
        var skipped: Bool?
        var skippedAt: Date?
        var saved: Bool?
        var savedAt: Date?
        var shared: Bool?
        var sharedAt: Date?

        private enum CodingKeys: String, CodingKey, CaseIterable {
            case notificationDelivered, notificationDeliveredAt, notificationOpened, notificationOpenedAt
            case appOpened, appOpenedAt, responded, respondedAt, skipped, skippedAt, saved, savedAt, shared, sharedAt
        }

        func encode(to encoder: Encoder) throws {
            var container = encoder.container(keyedBy: CodingKeys.self)
            try container.encode(notificationDelivered, forKey: .notificationDelivered)
            try container.encode(notificationDeliveredAt, forKey: .notificationDeliveredAt)
            try container.encode(notificationOpened, forKey: .notificationOpened)
            try container.encode(notificationOpenedAt, forKey: .notificationOpenedAt)
            try container.encode(appOpened, forKey: .appOpened)
            try container.encode(appOpenedAt, forKey: .appOpenedAt)
            try container.encode(responded, forKey: .responded)
            try container.encode(respondedAt, forKey: .respondedAt)
            try container.encode(skipped, forKey: .skipped)
            try container.encode(skippedAt, forKey: .skippedAt)
            try container.encode(saved, forKey: .saved)
            try container.encode(savedAt, forKey: .savedAt)
            try container.encode(shared, forKey: .shared)
            try container.encode(sharedAt, forKey: .sharedAt)
        }
    }

    var hasValidAssignment: Bool {
        stimulus.assignedProbability.isFinite && stimulus.assignedProbability > 0 && stimulus.assignedProbability <= 1
    }

    func containsInObservationWindow(_ date: Date) -> Bool {
        date >= decisionPointAt && date <= decisionPointAt.addingTimeInterval(TimeInterval(outcomeWindowSec))
    }

    mutating func observe(_ event: ManagerBenchEvent, at date: Date) {
        guard containsInObservationWindow(date) else { return }
        switch event {
        case .notificationDelivered:
            response.notificationDelivered = true
            response.notificationDeliveredAt = earliest(response.notificationDeliveredAt, date)
            stimulus.deliveredAt = earliest(stimulus.deliveredAt, date)
        case .notificationOpened:
            response.notificationOpened = true
            response.notificationOpenedAt = earliest(response.notificationOpenedAt, date)
        case .appOpened:
            response.appOpened = true
            response.appOpenedAt = earliest(response.appOpenedAt, date)
        case .responded:
            response.responded = true
            response.respondedAt = earliest(response.respondedAt, date)
        case .skipped:
            response.skipped = true
            response.skippedAt = earliest(response.skippedAt, date)
        case .saved:
            response.saved = true
            response.savedAt = earliest(response.savedAt, date)
        case .shared:
            response.shared = true
            response.sharedAt = earliest(response.sharedAt, date)
        }
    }

    mutating func closeObservationWindow(at date: Date) {
        let end = decisionPointAt.addingTimeInterval(TimeInterval(outcomeWindowSec))
        guard date >= end, observationWindowClosedAt == nil else { return }
        observationWindowClosedAt = end
        // These actions have durable callbacks in this app. A missing APNs receipt is
        // not evidence of non-delivery: iOS does not report background delivery here.
        if source == "notification", response.appOpened == nil { response.appOpened = false }
        if source != "notification" || response.notificationOpened == true {
            if response.saved == nil { response.saved = false }
            if response.shared == nil { response.shared = false }
        }
        if source == "onboarding_first_intervention", response.responded == nil { response.responded = false }
        if response.notificationDelivered == true, response.notificationOpened == nil { response.notificationOpened = false }
    }

    private func earliest(_ existing: Date?, _ date: Date) -> Date { existing.map { min($0, date) } ?? date }

    static var encoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }

    static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}

enum ManagerBenchEvent: String, Codable {
    case notificationDelivered = "notification_delivered"
    case notificationOpened = "notification_opened"
    case appOpened = "app_opened"
    case responded, skipped, saved, shared
}

/// Evidence awaiting a sender assignment; never exported as a complete eval case.
struct PendingDecisionObservation: Codable, Equatable {
    let personId: String
    let deliveryId: String
    var messageId: String? = nil
    let event: ManagerBenchEvent
    let observedAt: Date
}
