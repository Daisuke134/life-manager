import SwiftUI
import UIKit
import Combine
import StoreKit
import RevenueCat
import RevenueCatUI

struct MainTabView: View {
    @EnvironmentObject private var appState: AppState
    @State private var showUpgradePaywall = false

    var body: some View {
        MyPathTabView()
            .environmentObject(appState)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .fullScreenCover(item: $appState.pendingNudgeCard) { content in
                NudgeCardView(
                    content: content,
                    onPositiveAction: {
                        handleNudgeCardCompletion(content: content)
                    },
                    onNegativeAction: {
                        handleNudgeCardCompletion(content: content)
                    },
                    onFeedback: { isPositive in
                        if isPositive {
                            NudgeStatsManager.shared.recordThumbsUp(
                                problemType: content.problemType.rawValue,
                                variantIndex: content.variantIndex
                            )
                        } else {
                            NudgeStatsManager.shared.recordThumbsDown(
                                problemType: content.problemType.rawValue,
                                variantIndex: content.variantIndex
                            )
                        }
                    },
                    onDismiss: {
                        appState.dismissNudgeCard()
                    }
                )
            }
            .fullScreenCover(isPresented: $showUpgradePaywall) {
                upgradePaywallView()
            }
            .task {
                // Free ユーザーの日替わりローテーション再スケジュール
                if !appState.subscriptionInfo.isEntitled {
                    let problems = appState.userProfile.struggles.compactMap { ProblemType(rawValue: $0) }
                    FreePlanService.shared.rescheduleIfNeeded(problems: problems)
                }
            }
            .background(AppBackground())
            .ignoresSafeArea(.keyboard, edges: .bottom)
    }

    private func handleNudgeCardCompletion(content: NudgeContent) {
        appState.incrementNudgeCardCompletedCount()
        let count = appState.nudgeCardCompletedCount
        appState.dismissNudgeCard()

        // Free ユーザーのみ: 3回目 or 7回目に Paywall 表示
        if (count == 3 || count == 7) && !appState.subscriptionInfo.isEntitled {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                showUpgradePaywall = true
            }
            return
        }
    }

    @ViewBuilder
    private func upgradePaywallView() -> some View {
        PaywallVariantBView(
            variant: "rc_experiment",
            onPurchaseSuccess: { customerInfo in handleUpgradePurchase(customerInfo: customerInfo) },
            onDismiss: { showUpgradePaywall = false }
        )
    }

    private func handleUpgradePurchase(customerInfo: CustomerInfo) {
        AnalyticsManager.shared.track(.purchaseCompleted)
        Task {
            appState.updateSubscriptionInfo(from: customerInfo)
            await ProblemNotificationScheduler.shared
                .scheduleNotifications(for: appState.userProfile.struggles)
            showUpgradePaywall = false
        }
    }
}
