import Foundation
import RevenueCat

@Observable
@MainActor
class SubscriptionService {
    var isPremium = false
    var offerings: Offerings?
    var isLoading = false
    var errorMessage: String?
    var freeUsesRemaining: Int = 3

    private let freeUsesKey = "free_translation_uses"
    private let lastResetKey = "free_uses_last_reset"
    private let maxFreeUses = 3

    init() {
        loadFreeUses()
    }

    func checkSubscriptionStatus() async {
        do {
            let customerInfo = try await Purchases.shared.customerInfo()
            isPremium = customerInfo.entitlements["premium"]?.isActive == true
        } catch {
            isPremium = false
        }
    }

    func fetchOfferings() async {
        isLoading = true
        defer { isLoading = false }
        do {
            offerings = try await Purchases.shared.offerings()
        } catch {
            errorMessage = "プランの取得に失敗しました"
        }
    }

    func purchase(package: Package) async -> Bool {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let result = try await Purchases.shared.purchase(package: package)
            isPremium = result.customerInfo.entitlements["premium"]?.isActive == true
            return isPremium
        } catch {
            if let purchaseError = error as? RevenueCat.ErrorCode, purchaseError == .purchaseCancelledError {
                return false
            }
            errorMessage = "購入に失敗しました。もう一度お試しください。"
            return false
        }
    }

    func restorePurchases() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let customerInfo = try await Purchases.shared.restorePurchases()
            isPremium = customerInfo.entitlements["premium"]?.isActive == true
            if !isPremium {
                errorMessage = "復元できる購入が見つかりませんでした"
            }
        } catch {
            errorMessage = "復元に失敗しました"
        }
    }

    func canUseTranslation() -> Bool {
        if isPremium { return true }
        resetFreeUsesIfNeeded()
        return freeUsesRemaining > 0
    }

    func consumeFreeUse() {
        guard !isPremium else { return }
        freeUsesRemaining = max(0, freeUsesRemaining - 1)
        UserDefaults.standard.set(maxFreeUses - freeUsesRemaining, forKey: freeUsesKey)
    }

    private func loadFreeUses() {
        resetFreeUsesIfNeeded()
        let usedCount = UserDefaults.standard.integer(forKey: freeUsesKey)
        freeUsesRemaining = max(0, maxFreeUses - usedCount)
    }

    private func resetFreeUsesIfNeeded() {
        let lastReset = UserDefaults.standard.object(forKey: lastResetKey) as? Date ?? .distantPast
        if !Calendar.current.isDateInToday(lastReset) {
            UserDefaults.standard.set(0, forKey: freeUsesKey)
            UserDefaults.standard.set(Date(), forKey: lastResetKey)
            freeUsesRemaining = maxFreeUses
        }
    }
}
