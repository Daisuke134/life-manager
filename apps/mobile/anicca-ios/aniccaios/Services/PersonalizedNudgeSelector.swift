import Foundation

/// Rule v2 for choosing the next personalized intervention (first
/// intervention in onboarding, later the per-slot notification content).
///
/// Implements the synthesis rules of
/// `files/onboarding-answer-change-mapping-2026-11-14.md`:
/// 1. The user's explicit choices win over every proposal.
/// 2. `desired_state` is the primary category; `pain_point_ids` add boost
///    categories; candidates matching both rank first.
/// 3. Ties break by: not recently shown → outside the 14-day message
///    cooldown → fits the current time band. The candidate set, policy
///    version, and reason are recorded at every decision point.
/// 4. Selection is ε-greedy (ε = 0.1) so later causal measurement
///    (MRT / WCLS) has a known, non-degenerate assignment probability for
///    every chosen message. The exact probability of the chosen message is
///    returned and must be stored with the decision record — never
///    reconstructed afterwards.
enum PersonalizedNudgeSelector {
    static let policyVersion = "rule_v3_synthetic_user"
    static let explorationProbability = 0.1
    static let cooldownDays = 14

    enum TimeBand: String {
        case morning, day, evening, night

        static func band(forHour hour: Int) -> TimeBand {
            switch hour {
            case 5..<11: return .morning
            case 11..<17: return .day
            case 17..<22: return .evening
            default: return .night
            }
        }
    }

    struct Selection {
        let quote: Quote
        /// Human-readable reason code, stored with the decision record.
        let reason: String
        /// Size of the candidate set the choice was made from.
        let candidateCount: Int
        /// Exact probability of this quote under the ε-greedy policy.
        let assignedProbability: Double
        let policyVersion: String
    }

    /// Categories the profile asks for, primary first.
    static func preferredCategories(user: SyntheticUser) -> [String] {
        let profile = user.conditioningProfile
        if !profile.hasAnswers, let legacy = user.legacySignals { return legacy.preferredCategories.sorted() }
        var ordered: [String] = []
        if let primary = PersonalizationRules.primaryCategory(desiredState: profile.desiredState) {
            ordered.append(primary)
        }
        for painPointId in profile.painPointIds {
            for category in PersonalizationRules.boostCategories(painPointId: painPointId) where !ordered.contains(category) {
                ordered.append(category)
            }
        }
        return ordered
    }

    static func score(quote: Quote, user: SyntheticUser) -> Int {
        let profile = user.conditioningProfile
        if !profile.hasAnswers, let legacy = user.legacySignals {
            return legacy.preferredCategories.contains(quote.categoryID) ? 2 : 0
        }
        var value = 0
        if let primary = PersonalizationRules.primaryCategory(desiredState: profile.desiredState),
           quote.categoryID == primary {
            value += 2
        }
        let boosts = Set(profile.painPointIds.flatMap(PersonalizationRules.boostCategories))
        if boosts.contains(quote.categoryID) {
            value += 1
        }
        guard profile.adaptiveAnswers != nil else { return value }
        value *= 100 // desired state remains primary; other axes refine it.
        guard let traits = AdaptiveAffirmationCatalog.traits(for: quote) else { return value }
        let snapshot = user.answerSnapshot.values
        let themes = Set(profile.answers.ids(for: .beliefThemes))
        value += Set(traits.beliefThemes).intersection(themes).count * 5
        for (axis, options) in traits.answerMatches {
            if !Set(options).isDisjoint(with: snapshot[axis] ?? []) { value += 15 }
        }
        if traits.intensity == PersonalizationRules.intensity(profile: profile) { value += 2 }
        if traits.milestone != nil { value += 5 }
        return value
    }

    /// Eligibility runs before cooldown and exploration. Unknown editorial tags
    /// cannot establish that a message respects the new answers.
    static func isEligible(quote: Quote, user: SyntheticUser, band: TimeBand) -> Bool {
        let profile = user.conditioningProfile
        guard let traits = AdaptiveAffirmationCatalog.traits(for: quote) else {
            return profile.adaptiveAnswers == nil
        }
        // Legacy users keep the legacy pool until they answer the new questions.
        guard profile.adaptiveAnswers != nil else { return false }
        if PersonalizationRules.intensity(profile: profile) == "gentle", traits.intensity != "gentle" { return false }
        if let tone = profile.answers.ids(for: .tone).first, traits.tone != tone { return false }
        let contexts = Set(profile.answers.ids(for: .lifeContext))
        if !Set(traits.contexts).isSubset(of: contexts) { return false }
        let snapshot = user.answerSnapshot.values
        for (axis, options) in traits.answerMatches {
            if Set(options).isDisjoint(with: snapshot[axis] ?? []) { return false }
        }
        if !Set(traits.methods).isDisjoint(with: snapshot["prior_helpfulness"] ?? []) { return false }
        if !traits.timeBands.isEmpty, !traits.timeBands.contains(band.rawValue) { return false }
        if traits.milestone == "birthday_season", user.preferences["birthday_season"] != ["active"] { return false }
        return true
    }

    /// - Parameters:
    ///   - shownAt: message id → last time it was shown (decision history).
    ///   - random: uniform [0, 1) source, injected for testability.
    static func select(
        user: SyntheticUser,
        pool: [Quote],
        shownAt: [String: Date] = [:],
        now: Date = Date(),
        band: TimeBand,
        random: () -> Double = { Double.random(in: 0..<1) }
    ) -> Selection? {
        guard !pool.isEmpty else { return nil }
        let profile = user.conditioningProfile
        let shownAt = user.shownTimestamps.merging(shownAt, uniquingKeysWith: max)

        // Time-band fit: rest/sleep content is not sent in the morning
        // unless sleep is one of the user's own pain points.
        var candidates = pool.filter { isEligible(quote: $0, user: user, band: band) }
        if band == .morning, !profile.painPointIds.contains("sleep") {
            let nonRest = candidates.filter { $0.categoryID != "rest" }
            if !nonRest.isEmpty { candidates = nonRest }
        }
        let recent = Set(user.legacySignals?.recentMessageIDs ?? [])
        let unseen = candidates.filter { !recent.contains($0.id) }
        if !unseen.isEmpty { candidates = unseen }

        // 14-day message cooldown; if everything is in cooldown the pool
        // reopens rather than sending nothing.
        let cooldownCutoff = now.addingTimeInterval(-Double(cooldownDays) * 86_400)
        let fresh = candidates.filter { quote in
            guard let last = shownAt[quote.id] else { return true }
            return last < cooldownCutoff
        }
        if !fresh.isEmpty { candidates = fresh }

        // Deterministic ranking: score desc, unseen first, then id — so the
        // greedy pick is stable and the recorded reason is reproducible.
        let ranked = candidates.sorted { lhs, rhs in
            let lScore = score(quote: lhs, user: user)
            let rScore = score(quote: rhs, user: user)
            if lScore != rScore { return lScore > rScore }
            let lSeen = shownAt[lhs.id] != nil
            let rSeen = shownAt[rhs.id] != nil
            if lSeen != rSeen { return !lSeen }
            return lhs.id < rhs.id
        }
        guard let top = ranked.first else { return nil }

        let count = ranked.count
        let epsilon = explorationProbability
        let chosen: Quote
        if count > 1, random() < epsilon {
            let index = min(Int(random() * Double(count)), count - 1)
            chosen = ranked[index]
        } else {
            chosen = top
        }
        let probability = (chosen.id == top.id ? (1 - epsilon) : 0) + epsilon / Double(count)

        let chosenScore = score(quote: chosen, user: user)
        let reason: String
        if profile.adaptiveAnswers != nil {
            reason = "adaptive_answer_match"
        } else if !profile.hasAnswers, user.legacySignals != nil, chosenScore > 0 {
            reason = "legacy_preference_match"
        } else if chosenScore >= 3 {
            reason = "desired_state_and_pain_point_match"
        } else if chosenScore == 2 {
            reason = "desired_state_match"
        } else if chosenScore == 1 {
            reason = "pain_point_match"
        } else {
            reason = "fallback_unseen_first"
        }

        return Selection(
            quote: chosen,
            reason: reason,
            candidateCount: count,
            assignedProbability: probability,
            policyVersion: policyVersion
        )
    }
}
