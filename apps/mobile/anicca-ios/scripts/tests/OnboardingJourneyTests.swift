import Foundation

@main
struct OnboardingJourneyTests {
    static func main() {
        let journey = OnboardingStep.initialJourney
        precondition(journey == [.welcome, .goal, .name, .birthContext, .moodBaseline, .painPoints, .struggleFreq, .beliefThemes, .tone, .lifeContext, .routineAnchors, .priorAttempts, .startReason, .quietHours, .planReveal, .nudgeTimes, .notifications])
        precondition(OnboardingStep.welcome.nextInitialStep == .goal)
        precondition(OnboardingStep.goal.nextInitialStep == .name, "Ask the device-only form of address separately from the goal")
        precondition(OnboardingStep.name.nextInitialStep == .birthContext)
        precondition(OnboardingStep(rawValue: 9)?.resumableStep(painPointIds: []) == .name)
        precondition(OnboardingStep.painPoints.nextInitialStep == .struggleFreq)
        precondition(OnboardingStep.struggleFreq.nextInitialStep == .beliefThemes)
        precondition(OnboardingStep.planReveal.nextInitialStep == .nudgeTimes)
        precondition(OnboardingStep.nudgeTimes.nextInitialStep == .notifications)
        precondition(OnboardingStep.notifications.nextInitialStep == nil)
        precondition(OnboardingStep.welcome.resumableInitialStep == .welcome)
        precondition(OnboardingStep.processing.resumableInitialStep == .planReveal)
        precondition(OnboardingStep.comparison.resumableInitialStep == .planReveal)
        precondition(OnboardingStep.name.rawValue == 9, "New steps must not renumber persisted answers")
        for old in OnboardingStep.allCases {
            precondition(journey.contains(old.resumableStep(painPointIds: [])), "Every saved step must resume in the current journey")
        }
        precondition(OnboardingStep.deepDiveSteps(painPointIds: ["sleep", "anxiety"]) == [.anxietyTarget, .sleepReason, .bedtime, .wakeTime])
        precondition(OnboardingStep.deepDiveSteps(painPointIds: ["sleep", "stress", "self_doubt", "anxiety"]) == [.stressTrigger, .anxietyTarget])
        precondition(OnboardingStep.painPoints.nextStep(painPointIds: ["sleep", "anxiety"]) == .anxietyTarget)
        precondition(OnboardingStep.priorAttempts.nextStep(painPointIds: [], priorAttempts: ["first_time"]) == .startReason)
        precondition(OnboardingStep.priorAttempts.nextStep(painPointIds: [], priorAttempts: ["meditation"]) == .priorHelpfulness)
        print("OnboardingJourneyTests: PASS")
    }
}
