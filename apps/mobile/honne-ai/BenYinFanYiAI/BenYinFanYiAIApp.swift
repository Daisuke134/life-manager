import SwiftUI
import RevenueCat

@main
struct BenYinFanYiAIApp: App {
    @State private var aiService = AIService()
    @State private var subscriptionService = SubscriptionService()
    @State private var historyService = HistoryService()
    @State private var hasCompletedOnboarding = UserDefaults.standard.bool(forKey: "hasCompletedOnboarding")

    init() {
        #if DEBUG
        Purchases.logLevel = .debug
        Purchases.configure(withAPIKey: Config.EXPO_PUBLIC_REVENUECAT_TEST_API_KEY)
        #else
        Purchases.configure(withAPIKey: Config.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY)
        #endif
    }

    var body: some Scene {
        WindowGroup {
            if hasCompletedOnboarding {
                ContentView()
                    .environment(aiService)
                    .environment(subscriptionService)
                    .environment(historyService)
                    .task {
                        await subscriptionService.checkSubscriptionStatus()
                    }
            } else {
                OnboardingView {
                    UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")
                    hasCompletedOnboarding = true
                }
                .environment(subscriptionService)
                .task {
                    await subscriptionService.checkSubscriptionStatus()
                }
            }
        }
    }
}
