import Foundation

/// Explicit editorial tags, independent of language. Missing tags are not inferred
/// from text or from demographic answers.
struct AffirmationTraits {
    let tone: String
    let intensity: String
    var beliefThemes: [String] = []
    var contexts: [String] = []
    var answerMatches: [String: [String]] = [:]
    var methods: [String] = []
    var timeBands: [String] = []
    var milestone: String? = nil
}

/// A small explicitly tagged vocabulary for the adaptive onboarding answers. Generic
/// gentle candidates remain available in every style and desired-state category.
enum AdaptiveAffirmationCatalog {
    private struct Entry {
        let category: String
        let key: String
        let english: String
        let traits: AffirmationTraits

        var id: String { "adaptive.\(category).\(key)" }
    }

    static func traits(for quote: Quote) -> AffirmationTraits? {
        traitsByID[quote.id]
    }

    static func quotes(language: LanguagePreference) -> [Quote] {
        let languageBundle = Bundle.main.path(forResource: language.rawValue, ofType: "lproj")
            .flatMap { Bundle(path: $0) }
        let englishBundle = Bundle.main.path(forResource: "en", ofType: "lproj")
            .flatMap { Bundle(path: $0) }
        let bundle = languageBundle ?? englishBundle ?? Bundle.main
        return entries.map { entry in
            Quote(id: entry.id, text: bundle.localizedString(
                forKey: entry.key,
                value: entry.english,
                table: "AdaptiveAffirmations"
            ))
        }
    }

    private static let traitsByID = Dictionary(uniqueKeysWithValues: entries.map { ($0.id, $0.traits) })

    private static let entries: [Entry] = [
        Entry(
            category: "calm", key: "calm_gentle",
            english: "I can let this moment ask a little less of me.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["inner_peace"])
        ),
        Entry(
            category: "calm", key: "calm_direct",
            english: "I do not have to solve everything right now.",
            traits: AffirmationTraits(tone: "direct", intensity: "gentle", beliefThemes: ["inner_peace"])
        ),
        Entry(
            category: "calm", key: "calm_poetic",
            english: "I can leave a little room for quiet between the waves of today.",
            traits: AffirmationTraits(tone: "poetic", intensity: "gentle", beliefThemes: ["inner_peace"])
        ),
        Entry(
            category: "calm", key: "calm_practical",
            english: "I can loosen my shoulders and pause before the next thing.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["inner_peace"])
        ),
        Entry(
            category: "confidence", key: "confidence_gentle",
            english: "I can trust one small choice without knowing the whole way.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["self_trust"])
        ),
        Entry(
            category: "confidence", key: "confidence_direct",
            english: "Uncertainty does not erase what I already know.",
            traits: AffirmationTraits(tone: "direct", intensity: "gentle", beliefThemes: ["self_trust"])
        ),
        Entry(
            category: "confidence", key: "confidence_poetic",
            english: "My voice can be quiet and still have a place in the room.",
            traits: AffirmationTraits(tone: "poetic", intensity: "gentle", beliefThemes: ["self_trust", "courage"])
        ),
        Entry(
            category: "confidence", key: "confidence_practical",
            english: "I can name one thing I handled before and begin there.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["self_trust"])
        ),
        Entry(
            category: "presence", key: "presence_gentle",
            english: "I can return to one small part of this moment.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["inner_peace"])
        ),
        Entry(
            category: "presence", key: "presence_direct",
            english: "One thing at a time is enough for now.",
            traits: AffirmationTraits(tone: "direct", intensity: "gentle", beliefThemes: ["inner_peace"])
        ),
        Entry(
            category: "presence", key: "presence_poetic",
            english: "I can notice one small light in this ordinary moment.",
            traits: AffirmationTraits(tone: "poetic", intensity: "gentle", beliefThemes: ["gratitude"])
        ),
        Entry(
            category: "presence", key: "presence_practical",
            english: "I can notice my feet on the floor before choosing what comes next.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["inner_peace"])
        ),
        Entry(
            category: "self_love", key: "self_love_gentle",
            english: "I can be on my own side, even on a difficult day.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["forgiveness"])
        ),
        Entry(
            category: "self_love", key: "self_love_direct",
            english: "A mistake is something I did, not all of who I am.",
            traits: AffirmationTraits(tone: "direct", intensity: "gentle", beliefThemes: ["forgiveness"])
        ),
        Entry(
            category: "self_love", key: "self_love_poetic",
            english: "I can make a little shelter of kindness for the unfinished parts of me.",
            traits: AffirmationTraits(tone: "poetic", intensity: "gentle", beliefThemes: ["forgiveness"])
        ),
        Entry(
            category: "self_love", key: "self_love_practical",
            english: "I can replace one harsh thought with the words I would offer a friend.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["forgiveness"])
        ),
        Entry(
            category: "calm", key: "stress_work",
            english: "Between work tasks, I can let my shoulders settle for a moment.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["inner_peace"], contexts: ["work"], answerMatches: ["stress_trigger": ["work"]], timeBands: ["day"])
        ),
        Entry(
            category: "calm", key: "stress_social",
            english: "After being with others, I can take a quiet moment without explaining it.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["stress_trigger": ["social"]])
        ),
        Entry(
            category: "presence", key: "stress_morning",
            english: "I can meet this morning one small moment at a time.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["stress_trigger": ["morning"]], timeBands: ["morning"])
        ),
        Entry(
            category: "rest", key: "stress_night",
            english: "Tonight, I can set down one thing that can wait.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["stress_trigger": ["night"]], timeBands: ["evening", "night"])
        ),
        Entry(
            category: "presence", key: "anxiety_future",
            english: "I can separate what needs attention today from what has not happened yet.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["anxiety_target": ["future"]])
        ),
        Entry(
            category: "confidence", key: "anxiety_judgment",
            english: "I do not have to know everyone’s opinion to treat myself with respect.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["self_trust"], answerMatches: ["anxiety_target": ["judgment"]])
        ),
        Entry(
            category: "calm", key: "anxiety_health",
            english: "While health questions feel uncertain, I can meet myself with patience.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["anxiety_target": ["health"]])
        ),
        Entry(
            category: "presence", key: "anxiety_money",
            english: "When money worries grow, I can name one fact and leave the guesses for later.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["anxiety_target": ["money"]])
        ),
        Entry(
            category: "self_love", key: "criticism_work",
            english: "A mistake at work can need a repair without becoming a verdict on me.",
            traits: AffirmationTraits(tone: "direct", intensity: "gentle", beliefThemes: ["self_trust", "forgiveness"], contexts: ["work"], answerMatches: ["self_criticism": ["work"]])
        ),
        Entry(
            category: "confidence", key: "criticism_relationships",
            english: "A difficult conversation does not erase my capacity to care.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["self_trust", "forgiveness"], answerMatches: ["self_criticism": ["relationships"]])
        ),
        Entry(
            category: "self_love", key: "criticism_appearance",
            english: "My reflection does not have to pass a test for me to deserve kindness.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["self_trust", "forgiveness"], answerMatches: ["self_criticism": ["appearance"]])
        ),
        Entry(
            category: "self_love", key: "criticism_parenting",
            english: "A hard moment of parenting does not erase the care I bring.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["self_trust", "forgiveness"], contexts: ["caregiving"], answerMatches: ["self_criticism": ["parenting"]])
        ),
        Entry(
            category: "growth", key: "action_work",
            english: "I can spend two minutes opening the work task and naming its first step.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["courage"], contexts: ["work"], answerMatches: ["avoidance_task": ["work"]])
        ),
        Entry(
            category: "growth", key: "action_messages",
            english: "I can spend two minutes drafting one reply, without having to send it yet.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["courage"], answerMatches: ["avoidance_task": ["messages"]])
        ),
        Entry(
            category: "growth", key: "action_chores",
            english: "I can put away one thing in two minutes and let that be a beginning.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["courage"], answerMatches: ["avoidance_task": ["chores"]])
        ),
        Entry(
            category: "growth", key: "action_personal_plan",
            english: "I can spend two minutes choosing one small step for a plan that matters to me.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["courage"], answerMatches: ["avoidance_task": ["personal_plan"]])
        ),
        Entry(
            category: "rest", key: "sleep_racing_mind",
            english: "I do not have to finish every thought before allowing myself to rest.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["sleep_reason": ["racing_mind"]], timeBands: ["evening", "night"])
        ),
        Entry(
            category: "rest", key: "sleep_body_clock",
            english: "I can make room for rest without demanding that sleep arrive on command.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["sleep_reason": ["body_clock"]], timeBands: ["evening", "night"])
        ),
        Entry(
            category: "rest", key: "sleep_screens",
            english: "I can put my screen face down for a moment and give this evening a softer pace.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["sleep_reason": ["screens"]], timeBands: ["evening", "night"])
        ),
        Entry(
            category: "calm", key: "start_overwhelmed",
            english: "For this moment, I can let one small pause be enough.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["start_reason": ["overwhelmed"]])
        ),
        Entry(
            category: "growth", key: "start_new_chapter",
            english: "A new chapter can begin with a step small enough for today.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["courage"], contexts: ["transition"], answerMatches: ["start_reason": ["new_chapter"]])
        ),
        Entry(
            category: "self_love", key: "start_recommended",
            english: "I can explore what someone suggested while keeping my own pace.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["self_trust"], answerMatches: ["start_reason": ["recommended"]])
        ),
        Entry(
            category: "presence", key: "start_curious",
            english: "I can notice how one sentence feels without deciding what comes after.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", answerMatches: ["start_reason": ["curious"]])
        ),
        Entry(
            category: "letting_go", key: "birthday_season",
            english: "In this birthday season, I can notice what I want to carry into the year ahead.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["gratitude"], milestone: "birthday_season")
        ),
        Entry(
            category: "presence", key: "method_meditation",
            english: "I can return to one familiar moment of meditation, without needing a perfect session.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["prior_attempts": ["meditation"]], methods: ["meditation"])
        ),
        Entry(
            category: "self_love", key: "method_journaling",
            english: "I can write one honest sentence in my journal and let that be enough.",
            traits: AffirmationTraits(tone: "practical", intensity: "gentle", beliefThemes: ["self_trust"], answerMatches: ["prior_attempts": ["journaling"]], methods: ["journaling"])
        ),
        Entry(
            category: "confidence", key: "method_therapy",
            english: "I can recall one helpful idea from a past therapy conversation, at my own pace.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["self_trust"], answerMatches: ["prior_attempts": ["therapy"]], methods: ["therapy"])
        ),
        Entry(
            category: "calm", key: "method_books",
            english: "I can revisit one line from a book that felt kind to me.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["inner_peace"], answerMatches: ["prior_attempts": ["books"]], methods: ["books"])
        ),
        Entry(
            category: "calm", key: "calm_supportive",
            english: "I can make one small choice today that leaves more room for calm.",
            traits: AffirmationTraits(tone: "direct", intensity: "supportive", beliefThemes: ["inner_peace"])
        ),
        Entry(
            category: "confidence", key: "confidence_supportive",
            english: "I can take one small step before I feel completely ready.",
            traits: AffirmationTraits(tone: "direct", intensity: "supportive", beliefThemes: ["self_trust", "courage"])
        ),
        Entry(
            category: "presence", key: "presence_supportive",
            english: "I can choose one thing that matters and give it my attention for the next minute.",
            traits: AffirmationTraits(tone: "direct", intensity: "supportive", beliefThemes: ["inner_peace"])
        ),
        Entry(
            category: "self_love", key: "self_love_supportive",
            english: "I can practice being on my own side through one kind choice today.",
            traits: AffirmationTraits(tone: "direct", intensity: "supportive", beliefThemes: ["forgiveness", "self_trust"])
        ),
        Entry(
            category: "gratitude", key: "gratitude_gentle",
            english: "I can notice one small thing I appreciate without needing the whole day to feel good.",
            traits: AffirmationTraits(tone: "gentle", intensity: "gentle", beliefThemes: ["gratitude"])
        ),
    ]
}
