import Foundation
import OSLog

/// Legacy v1/v2 decoder used only to migrate pre-ManagerBench local records.
/// One row per decision point, per the Phase 1 measurement contract in
/// `files/onboarding-answer-change-mapping-2026-11-14.md` and the
/// state-transition schema (1 row = 1 person × 1 decision point).
///
/// Two row kinds share this file:
/// - `decision`: made on device by `PersonalizedNudgeSelector`. Always
///   carries the exact `assignedProbability` of the chosen treatment
///   (required, never blank, never reconstructed afterwards).
/// - `outcome`: a later observation (delivered / opened / responded /
///   skipped) joined to its decision by `deliveryId`. For notifications
///   decided by the backend sender, the outcome row is the on-device half
///   of the record; the decision row lives with the sender.
///
/// Storage is on-device only (Application Support). Analytics receives IDs,
/// categories, and versions — never the user's name or free text.
struct DecisionPointRecord: Codable, Equatable {
    var recordKind: String              // "decision" | "outcome"
    var personId: String                // pseudonymous, device-generated UUID
    var deliveryId: String              // join key across decision + outcomes
    var decisionPointAt: String         // ISO-8601 UTC
    var available: Bool                 // user was available at the decision point
    var treatmentAssigned: String       // message id, or "do_not_send"
    var assignedProbability: Double?    // required on decision rows: 0 < p <= 1
    var messageId: String?
    var policyVersion: String
    var source: String                  // onboarding_first_intervention / notification / ...
    var desiredState: String?
    var painPointIds: [String]
    var struggleFrequency: String?
    var candidateCount: Int?
    var selectionReason: String?
    var proximalOutcome: String?        // nil = unobserved; delivered/opened/responded/skipped
    var outcomeWindowSec: Int
    var answerSnapshot: OnboardingAnswerSnapshot? = nil
}

final class DecisionPointStore {
    static let shared = DecisionPointStore()
    private let queue = DispatchQueue(label: "com.anicca.decision-points")
    private let directory: URL
    private let logger = Logger(subsystem: "com.anicca.ios", category: "DecisionPointStore")

    init(directory: URL? = nil) {
        self.directory = directory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Anicca", isDirectory: true)
        migrateLegacyRecords()
    }

    private var casesURL: URL { directory.appendingPathComponent("managerbench-cases.jsonl") }
    private var observationsURL: URL { directory.appendingPathComponent("pending-decision-observations.jsonl") }
    private var outsideWindowURL: URL { directory.appendingPathComponent("outside-window-observations.jsonl") }

    func allCases() -> [ManagerBenchCase] { queue.sync { loadCases() } }
    func pendingObservations() -> [PendingDecisionObservation] { queue.sync { loadObservations() } }
    func outsideWindowObservations() -> [PendingDecisionObservation] { queue.sync { load(PendingDecisionObservation.self, from: outsideWindowURL) } }

    /// Preserve the original occurrence IDs and measured times when upgrading
    /// the conditioning record. A legacy positive without a time is not dated.
    func syntheticInterventionHistory(personId: String) -> [SyntheticUser.Intervention] {
        queue.sync {
            var history: [SyntheticUser.Intervention] = []
            for row in loadCases() where row.personId == personId {
                history.append(.init(deliveryId: row.deliveryId, messageId: row.stimulus.messageId,
                                     event: .assigned, observedAt: row.decisionPointAt))
                let response = row.response
                let measured: [(SyntheticUser.InterventionEvent, Bool?, Date?)] = [
                    (.notificationDelivered, response.notificationDelivered, response.notificationDeliveredAt),
                    (.notificationOpened, response.notificationOpened, response.notificationOpenedAt),
                    (.appOpened, response.appOpened, response.appOpenedAt),
                    (.responded, response.responded, response.respondedAt),
                    (.skipped, response.skipped, response.skippedAt),
                    (.saved, response.saved, response.savedAt), (.shared, response.shared, response.sharedAt)
                ]
                for (event, occurred, date) in measured {
                    guard occurred == true, let date else { continue }
                    history.append(.init(deliveryId: row.deliveryId, messageId: row.stimulus.messageId, event: event, observedAt: date))
                }
            }
            let observations = loadObservations() + load(PendingDecisionObservation.self, from: outsideWindowURL)
            for observation in observations where observation.personId == personId {
                guard let event = SyntheticUser.InterventionEvent(rawValue: observation.event.rawValue) else { continue }
                history.append(.init(deliveryId: observation.deliveryId, messageId: observation.messageId,
                                     event: event, observedAt: observation.observedAt))
            }
            return history.sorted { $0.observedAt < $1.observedAt }
        }
    }

    @discardableResult
    func append(_ record: ManagerBenchCase) -> Bool {
        guard record.hasValidAssignment else { return false }
        return queue.sync {
            var records = loadCases()
            let index: Int
            if let existing = records.firstIndex(where: { $0.deliveryId == record.deliveryId && $0.personId == record.personId }) {
                index = existing
            } else {
                records.append(record)
                index = records.count - 1
            }
            let pending = loadObservations()
            let matching = pending.filter { $0.deliveryId == record.deliveryId && $0.personId == record.personId }
            for observation in matching {
                if records[index].containsInObservationWindow(observation.observedAt) {
                    records[index].observe(observation.event, at: observation.observedAt)
                } else if !persistOutsideWindow(observation) { return false }
            }
            guard write(records, to: casesURL) else { return false }
            if !matching.isEmpty {
                _ = write(pending.filter { $0.deliveryId != record.deliveryId || $0.personId != record.personId }, to: observationsURL)
            }
            return true
        }
    }

    @discardableResult
    func recordResponse(personId: String, deliveryId: String, event: ManagerBenchEvent, at date: Date, messageId: String? = nil) -> Bool {
        queue.sync {
            var records = loadCases()
            if let index = records.firstIndex(where: { $0.personId == personId && $0.deliveryId == deliveryId }) {
                if records[index].containsInObservationWindow(date) {
                    records[index].observe(event, at: date)
                    return write(records, to: casesURL)
                }
                return persistOutsideWindow(.init(personId: personId, deliveryId: deliveryId, messageId: messageId, event: event, observedAt: date))
            }
            var pending = loadObservations()
            let observation = PendingDecisionObservation(personId: personId, deliveryId: deliveryId, messageId: messageId, event: event, observedAt: date)
            if let index = pending.firstIndex(where: { $0.personId == personId && $0.deliveryId == deliveryId && $0.event == event }) {
                if pending[index].observedAt <= date { return true }
                pending[index] = observation
            } else { pending.append(observation) }
            return write(pending, to: observationsURL)
        }
    }

    func closeObservationWindows(at date: Date) {
        queue.sync {
            var records = loadCases()
            let original = records
            for index in records.indices { records[index].closeObservationWindow(at: date) }
            if records != original { _ = write(records, to: casesURL) }
        }
    }

    private func persistOutsideWindow(_ observation: PendingDecisionObservation) -> Bool {
        var observations = load(PendingDecisionObservation.self, from: outsideWindowURL)
        if !observations.contains(observation) { observations.append(observation) }
        return write(observations, to: outsideWindowURL)
    }

    private func loadCases() -> [ManagerBenchCase] { load(ManagerBenchCase.self, from: casesURL) }
    private func loadObservations() -> [PendingDecisionObservation] { load(PendingDecisionObservation.self, from: observationsURL) }

    private func load<T: Decodable>(_ type: T.Type, from url: URL) -> [T] {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        return text.split(separator: "\n").compactMap { try? ManagerBenchCase.decoder.decode(type, from: Data($0.utf8)) }
    }

    private func write<T: Encodable>(_ records: [T], to url: URL) -> Bool {
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let lines = try records.map { try ManagerBenchCase.encoder.encode($0) }
            var data = Data()
            for line in lines { data.append(line); data.append(0x0A) }
            try data.write(to: url, options: .atomic)
            return true
        } catch {
            logger.error("Unable to persist decision evidence (code: \((error as NSError).code))")
            return false
        }
    }

    /// The source journal is retained. Import is idempotent by person + delivery;
    /// unknown legacy probabilities never turn into invented assignments.
    private func migrateLegacyRecords() {
        let legacyURL = directory.appendingPathComponent("decision-points.jsonl")
        guard let text = try? String(contentsOf: legacyURL, encoding: .utf8) else { return }
        let decoder = JSONDecoder()
        let formatter = ISO8601DateFormatter()
        let records = text.split(separator: "\n").compactMap { try? decoder.decode(DecisionPointRecord.self, from: Data($0.utf8)) }
        for old in records where old.recordKind == "decision" {
            guard let probability = old.assignedProbability, let messageId = old.messageId,
                  let date = formatter.date(from: old.decisionPointAt) else { continue }
            var row = ManagerBenchCase(
                personId: old.personId, deliveryId: old.deliveryId, decisionPointAt: date,
                source: old.source, outcomeWindowSec: old.outcomeWindowSec,
                situation: .init(answerSnapshot: old.answerSnapshot?.values ?? [:], answerVersion: old.answerSnapshot?.version ?? 0,
                                 scheduledTimeBand: "unknown", weekday: "unknown", notificationPermission: "unknown"),
                stimulus: .init(messageId: messageId, category: "unknown", tags: [], scheduledAt: nil,
                                treatmentAssigned: old.treatmentAssigned, assignedProbability: probability, policyVersion: old.policyVersion)
            )
            // v1/v2 retained one positive outcome but no observation timestamp.
            // Preserve the known positive without inventing when it happened.
            switch old.proximalOutcome.flatMap({ Self.legacyEvent($0) }) {
            case .some(.notificationDelivered): row.response.notificationDelivered = true
            case .some(.notificationOpened): row.response.notificationOpened = true
            case .some(.appOpened): row.response.appOpened = true
            case .some(.responded): row.response.responded = true
            case .some(.skipped): row.response.skipped = true
            case .some(.saved): row.response.saved = true
            case .some(.shared): row.response.shared = true
            case nil: break
            }
            _ = append(row)
        }
        for old in records where old.recordKind == "outcome" {
            guard let date = formatter.date(from: old.decisionPointAt), let outcome = old.proximalOutcome,
                  let event = Self.legacyEvent(outcome) else { continue }
            _ = recordResponse(personId: old.personId, deliveryId: old.deliveryId, event: event, at: date, messageId: old.messageId)
        }
    }

    static func legacyEvent(_ value: String) -> ManagerBenchEvent? {
        switch value {
        case "delivered": return .notificationDelivered
        case "opened": return .notificationOpened
        default: return ManagerBenchEvent(rawValue: value)
        }
    }
}

@MainActor
final class DecisionPointRecorder {
    static let shared = DecisionPointRecorder()
    private let personIdKey = "com.anicca.decisionPersonId"
    private let outcomeWindowSec = 30 * 60
    private init() {}

    var personId: String {
        if let existing = UserDefaults.standard.string(forKey: personIdKey) { return existing }
        let created = UUID().uuidString
        UserDefaults.standard.set(created, forKey: personIdKey)
        return created
    }

    @discardableResult
    func recordDecision(selection: PersonalizedNudgeSelector.Selection, syntheticUser: SyntheticUser, source: String) -> String {
        let now = Date()
        let deliveryId = UUID().uuidString
        let snapshot = syntheticUser.answerSnapshot
        let traits = AdaptiveAffirmationCatalog.traits(for: selection.quote)
        let tags = (traits.map { [$0.tone, $0.intensity] + $0.beliefThemes + $0.contexts + $0.methods + $0.timeBands } ?? [])
        let calendar = Calendar.current
        let weekday = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"][calendar.component(.weekday, from: now) - 1]
        let record = ManagerBenchCase(
            personId: personId, deliveryId: deliveryId, decisionPointAt: now, source: source, outcomeWindowSec: outcomeWindowSec,
            situation: .init(answerSnapshot: snapshot.values, answerVersion: snapshot.version,
                             scheduledTimeBand: PersonalizedNudgeSelector.TimeBand.band(forHour: calendar.component(.hour, from: now)).rawValue,
                             weekday: weekday, notificationPermission: NotificationScheduler.shared.observedAuthorizationStatus,
                             notificationPermissionObservedAt: NotificationScheduler.shared.authorizationObservedAt),
            stimulus: .init(messageId: selection.quote.id, category: selection.quote.categoryID, tags: Array(Set(tags)).sorted(),
                            scheduledAt: now, treatmentAssigned: selection.quote.id,
                            assignedProbability: selection.assignedProbability, policyVersion: selection.policyVersion)
        )
        if DecisionPointStore.shared.append(record) {
            AppState.shared.recordSyntheticIntervention(messageId: selection.quote.id, deliveryId: deliveryId, event: "selected", at: now)
        }
        AnalyticsManager.shared.track(.nudgeDecisionMade, properties: [
            "delivery_id": deliveryId, "message_id": selection.quote.id, "category": selection.quote.categoryID,
            "assigned_probability": selection.assignedProbability, "policy_version": selection.policyVersion,
            "selection_reason": selection.reason, "answer_ids": snapshot.analyticsIDs, "answer_version": snapshot.version, "source": source
        ])
        return deliveryId
    }

    func recordResponse(deliveryId: String, event: ManagerBenchEvent, at date: Date = Date(), messageId: String? = nil) {
        guard DecisionPointStore.shared.recordResponse(personId: personId, deliveryId: deliveryId, event: event, at: date, messageId: messageId) else { return }
        let recordedMessageId = DecisionPointStore.shared.allCases().first { $0.personId == personId && $0.deliveryId == deliveryId }?.stimulus.messageId ?? messageId
        AppState.shared.recordSyntheticIntervention(messageId: recordedMessageId, deliveryId: deliveryId, event: event.rawValue, at: date)
    }

    func recordQuoteResponse(messageId: String, deliveryId: String? = nil, event: ManagerBenchEvent) {
        guard let deliveryId else { return }
        recordResponse(deliveryId: deliveryId, event: event, messageId: messageId)
    }

    func recordAppOpened(at date: Date = Date()) {
        for row in DecisionPointStore.shared.allCases() where row.personId == personId &&
            row.decisionPointAt <= date && date <= row.decisionPointAt.addingTimeInterval(TimeInterval(row.outcomeWindowSec)) {
            recordResponse(deliveryId: row.deliveryId, event: .appOpened, at: date)
        }
        DecisionPointStore.shared.closeObservationWindows(at: date)
    }

    /// A sender may attach its complete assignment using the same snake_case
    /// schema under decision_point. Missing metadata remains pending evidence.
    /// The device never reconstructs the sender's assignment probability.
    func recordNotificationAssignment(userInfo: [AnyHashable: Any], deliveryId: String) {
        guard var payload = userInfo["decision_point"] as? [String: Any] else { return }
        payload["person_id"] = personId
        payload["delivery_id"] = deliveryId
        payload["schema_version"] = 1
        payload["source"] = "notification"
        payload["outcome_window_sec"] = outcomeWindowSec
        payload["response"] = [String: Any]()
        payload.removeValue(forKey: "observation_window_closed_at")
        guard JSONSerialization.isValidJSONObject(payload),
              let data = try? JSONSerialization.data(withJSONObject: payload),
              var row = try? ManagerBenchCase.decoder.decode(ManagerBenchCase.self, from: data),
              row.hasValidAssignment, row.stimulus.scheduledAt != nil,
              row.stimulus.treatmentAssigned == row.stimulus.messageId,
              ["rule_v1", PersonalizedNudgeSelector.policyVersion].contains(row.stimulus.policyVersion),
              let quote = QuoteProvider.shared.byId(row.stimulus.messageId, preferredLanguage: AppState.shared.effectiveLanguage),
              Self.isEnumeratedSituation(row.situation) else { return }
        let traits = AdaptiveAffirmationCatalog.traits(for: quote)
        row.stimulus.category = quote.categoryID
        row.stimulus.tags = Array(Set(traits.map { [$0.tone, $0.intensity] + $0.beliefThemes + $0.contexts + $0.methods + $0.timeBands } ?? [])).sorted()
        // Delivery and human reactions come exclusively from OS/app callbacks.
        row.stimulus.deliveredAt = nil
        if DecisionPointStore.shared.append(row) {
            AppState.shared.recordSyntheticIntervention(messageId: quote.id, deliveryId: deliveryId, event: "selected", at: row.decisionPointAt)
        }
    }

    static func isEnumeratedSituation(_ situation: ManagerBenchCase.Situation) -> Bool {
        var vocabulary = Dictionary(uniqueKeysWithValues: OnboardingQuestion.allCases.map { ($0.rawValue, $0.optionIDs + ["unknown", "not_asked"]) })
        vocabulary["birth_context", default: []].append("date_provided")
        vocabulary["age_band"] = ["under_18", "18_24", "25_34", "35_44", "45_54", "55_64", "65_plus", "unknown"]
        vocabulary["desired_state"] = ["calm", "confidence", "focus", "self_love", "unknown"]
        vocabulary["pain_points"] = ["stress", "anxiety", "self_doubt", "procrastination", "sleep", "unknown"]
        vocabulary["struggle_frequency"] = ["rarely", "weekly", "daily", "many_times_daily", "unknown"]
        vocabulary["name_status"] = ["unknown", "provided"]
        vocabulary["notification_permission"] = ["allowed", "denied", "skipped", "unknown"]
        vocabulary["reminder_slots"] = PersonalizationRules.presetSlots.map { "slot_\($0.hour)_\($0.minute)" }
        vocabulary["daily_frequency"] = ["one", "two", "three", "unknown"]
        vocabulary["birthday_season"] = ["active", "inactive", "unknown"]
        let quotes = QuoteProvider.shared.all(preferredLanguage: .en)
        for key in ["legacy_goal_categories", "legacy_problem_categories", "legacy_liked_categories"] {
            vocabulary[key] = Array(Set(quotes.map(\.categoryID)))
        }
        vocabulary["legacy_recent_message_ids"] = quotes.map(\.id)
        return situation.answerSnapshot.allSatisfy { axis, values in
            guard let allowed = vocabulary[axis] else { return false }
            return values.allSatisfy { allowed.contains($0) }
        } && ["morning", "day", "evening", "night", "unknown"].contains(situation.scheduledTimeBand)
            && ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "unknown"].contains(situation.weekday)
            && ["authorized", "provisional", "ephemeral", "denied", "not_determined", "unknown"].contains(situation.notificationPermission)
    }

    func recordNotificationOutcome(deliveryId: String, messageId: String?, outcome: String, at date: Date = Date()) {
        guard let event = DecisionPointStore.legacyEvent(outcome) else { return }
        let knownMessageId = messageId.flatMap { id in
            QuoteProvider.shared.byId(id, preferredLanguage: AppState.shared.effectiveLanguage)?.id
        }
        recordResponse(deliveryId: deliveryId, event: event, at: date, messageId: knownMessageId)
    }
}
