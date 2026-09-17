import RevenueCat
import Foundation
import AdSupport

@MainActor
final class SubscriptionManager: NSObject {
    static let shared = SubscriptionManager()
    private var offerings: Offerings?
    private(set) var isConfigured = false

    private override init() {
        super.init()
    }

    func configure() {
        // UIテストモード時はRevenueCat初期化をスキップ（CIシミュレータでApple IDダイアログを防止）
        if ProcessInfo.processInfo.arguments.contains("-UITESTING") {
            print("[RevenueCat] Skipped - UI testing mode")
            return
        }

        Purchases.logLevel = .info // .debugから変更（JWS tokenの長いログを抑制）
        let apiKey = AppConfig.revenueCatAPIKey
        print("[RevenueCat] Using API Key: \(apiKey)")
        
        // V2/StoreKit 2対応のシンプル構成
        // entitlementVerificationMode: .informational は推奨設定（検証結果を情報として提供）
        // 言語設定は自動検出されるため明示的な設定は不要
        Purchases.configure(
            with: Configuration.Builder(withAPIKey: apiKey)
                .with(entitlementVerificationMode: .informational)
                .build()
        )
        
        Purchases.shared.delegate = self

        // RevenueCat → Singular 連携に必須
        // $idfa（ATT なしの場合は all-zeros）と $idfv を RevenueCat に渡す
        // これがないと RevenueCat → Singular にイベントが送信されない
        Purchases.shared.attribution.collectDeviceIdentifiers()

        // 起動直後にSDKキャッシュのOfferingをAppStateへプリロード
        if let cached = Purchases.shared.cachedOfferings,
           let preloaded = cached.current {
            print("[SubscriptionManager] Pre-loading cached offering: \(preloaded.identifier)")
            AppState.shared.updateOffering(preloaded)
        }
        
        isConfigured = true

        // 起動直後にオファリング取得を開始（並列実行で高速化）
        Task {
            await withTaskGroup(of: Void.self) { group in
                group.addTask { await self.refreshOfferings() }
                group.addTask { await self.listenCustomerInfo() }
            }
        }
    }
    
    private func listenCustomerInfo() async {
        for await info in Purchases.shared.customerInfoStream {
            await MainActor.run {
                var subscription = SubscriptionInfo(info: info)
                
                // 重要: RevenueCatの情報を優先して即座に更新
                AppState.shared.updateSubscriptionInfo(subscription)
                
                // サーバーから月次利用量情報を取得してマージ（バックグラウンド）
                Task.detached(priority: .utility) {
                    await self.syncUsageInfo(&subscription)
                    // 利用量情報のみを更新（エンタイトルメント状態は変更しない）
                    await MainActor.run {
                        var currentSubscription = AppState.shared.subscriptionInfo
                        // エンタイトルメント状態を保持したまま、利用量情報のみ更新
                        currentSubscription.monthlyUsageLimit = subscription.monthlyUsageLimit
                        currentSubscription.monthlyUsageRemaining = subscription.monthlyUsageRemaining
                        currentSubscription.monthlyUsageCount = subscription.monthlyUsageCount
                        AppState.shared.updateSubscriptionInfo(currentSubscription)
                    }
                }
            }
        }
    }
    
    private func syncUsageInfo(_ subscription: inout SubscriptionInfo) async {
        // v0.5.1: 匿名ユーザーでも利用量情報を同期
        let deviceId = AppState.shared.resolveDeviceId()
        let userId: String
        if case .signedIn(let credentials) = AppState.shared.authStatus {
            userId = credentials.userId
        } else {
            userId = deviceId
        }
        
        var request = URLRequest(url: AppConfig.entitlementSyncURL)
        request.httpMethod = "GET"
        request.setValue(deviceId, forHTTPHeaderField: "device-id")
        request.setValue(userId, forHTTPHeaderField: "user-id")
        
        do {
            let (data, response) = try await NetworkSessionManager.shared.session.data(for: request)
            
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                print("[SubscriptionManager] Server sync failed (status \( (response as? HTTPURLResponse)?.statusCode ?? 0 )), proceeding with RC data.")
                return
            }
            
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let entitlement = json["entitlement"] as? [String: Any] {
                // 重要: 利用量情報のみを更新し、エンタイトルメント状態（plan, status）は上書きしない
                subscription.monthlyUsageLimit = entitlement["monthly_usage_limit"] as? Int
                subscription.monthlyUsageRemaining = entitlement["monthly_usage_remaining"] as? Int
                subscription.monthlyUsageCount = entitlement["monthly_usage_count"] as? Int
                
                print("[SubscriptionManager] Synced usage info only (plan/status unchanged): limit=\(subscription.monthlyUsageLimit ?? -1)")
            }
        } catch {
            print("[SubscriptionManager] Sync error: \(error). Using RC entitlement only.")
        }
    }
    
    func handleLogin(appUserId: String) async {
        guard isConfigured else { return }
        if Purchases.shared.appUserID != appUserId {
            _ = try? await Purchases.shared.logIn(appUserId)
        }
        await refreshOfferings()
    }
    
    func handleLogout() async {
        guard isConfigured else { return }
        // 匿名ユーザーの場合はログアウト不要
        guard !Purchases.shared.isAnonymous else {
            print("[RevenueCat] Skipping logout for anonymous user")
            return
        }
        _ = try? await Purchases.shared.logOut()
    }
    
    func refreshOfferings() async {
        guard isConfigured else { return }
        do {
            let result = try await Purchases.shared.offerings()
            print("[SubscriptionManager] Offerings loaded: current=\(result.current?.identifier ?? "nil"), all=\(result.all.keys.joined(separator: ", "))")
            offerings = result
            await MainActor.run {
                // キャッシュを確実に更新
                if let offering = result.current {
                    AppState.shared.updateOffering(offering)
                } else {
                    AppState.shared.updateOffering(nil)
                }
            }
        } catch {
            await MainActor.run {
                // Keep existing cached offering on error
                if AppState.shared.cachedOffering == nil {
                    AppState.shared.updateOffering(nil)
                }
            }
        }
    }
    
    func syncNow() async {
        guard isConfigured else { return }
        // 1) 端末側の領収書同期
        do {
            _ = try await Purchases.shared.syncPurchases()
        } catch {
            print("[SubscriptionManager] syncPurchases failed: \(error)")
        }
        
        // 2) サーバにRC再取得を要求（DB→/mobile/entitlement反映）
        // 重要(1.6.3): "通常状態ユーザー（= ほぼ全員）" でもサーバがPro/Freeを判定できるようにする。
        // - RevenueCatの購読状態は端末内では分かるが、APNs配信量はサーバが決めるため、サーバ側SSOT(user_subscriptions)の更新が必要。
        // - ここでは Sign in with Apple の userId ではなく、RevenueCatの appUserID を SSOT の鍵として送る。
        //   backendは device-id から profileId(UUID) を解決して user_subscriptions(user_id=profileId) を更新する。
        let deviceId = AppState.shared.resolveDeviceId()
        let revenueCatAppUserId = Purchases.shared.appUserID.trimmingCharacters(in: .whitespacesAndNewlines)
        let userIdHeader = revenueCatAppUserId.isEmpty ? deviceId : revenueCatAppUserId

        var request = URLRequest(url: AppConfig.proxyBaseURL.appendingPathComponent("billing/revenuecat/sync"))
        request.httpMethod = "POST"
        request.timeoutInterval = 10.0 // 10秒でタイムアウト
        request.setValue(deviceId, forHTTPHeaderField: "device-id")
        request.setValue(userIdHeader, forHTTPHeaderField: "user-id")
        
        do {
            let (_, response) = try await NetworkSessionManager.shared.session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                print("[SubscriptionManager] Invalid response type")
                return
            }
            
            if !(200..<300).contains(httpResponse.statusCode) {
                print("[SubscriptionManager] Sync failed with status: \(httpResponse.statusCode)")
                return
            }
            
            // 3) 最新Entitlementを取得
            var subscription = AppState.shared.subscriptionInfo
            await syncUsageInfo(&subscription)
            await MainActor.run {
                AppState.shared.updateSubscriptionInfo(subscription)
            }
        } catch {
            print("[SubscriptionManager] Sync error: \(error.localizedDescription)")
            // エラーでも続行（オフライン時など）
        }
    }
}

extension SubscriptionManager: PurchasesDelegate {
    func purchases(_ purchases: Purchases, receivedUpdated customerInfo: CustomerInfo) {
        print("[RevenueCat] Delegate received update. Active entitlements: \(customerInfo.entitlements.active.keys)")
        
        Task { @MainActor in
            let subscription = SubscriptionInfo(info: customerInfo)
            
            // 1. まずRevenueCatの情報だけで即座に更新（待機なし）
            AppState.shared.updateSubscriptionInfo(subscription)
            
            // 2. Mixpanelへ購入イベント送信（新規購入の場合のみ）
            if subscription.plan == .pro,
               let productId = subscription.productIdentifier {
                // 価格を取得（RevenueCatから）
                let price: Double
                if let offering = AppState.shared.cachedOffering,
                   let package = offering.availablePackages.first(where: { $0.storeProduct.productIdentifier == productId }) {
                    price = package.storeProduct.price as? Double ?? 9.99
                } else {
                    // フォールバック価格
                    price = 9.99
                }
                AnalyticsManager.shared.trackPurchaseCompleted(productId: productId, revenue: price)
            }
            
            // 3. サーバーDBを同期してからlimit情報を取得（POSTでDB更新→GET）
            await syncNow()
        }
    }
    
    // 追加: アプリ内課金のプロモーション対応（ベストプラクティス）
    func purchases(_ purchases: Purchases, readyForPromotedProduct product: StoreProduct, purchase: @escaping StartPurchaseBlock) {
        purchase { (transaction, info, error, cancelled) in
            if let info = info {
                Task { @MainActor in
                    let sub = SubscriptionInfo(info: info)
                    AppState.shared.updateSubscriptionInfo(sub)
                }
            }
        }
    }
}

@MainActor
extension SubscriptionInfo {
    init(info: CustomerInfo) {
        let configuredId = AppConfig.revenueCatEntitlementId
        let primaryEntitlement = info.entitlements[configuredId]
        let fallbackEntitlement = info.entitlements.active.values.first
        let entitlement = primaryEntitlement ?? fallbackEntitlement

        let plan: Plan
        if entitlement?.isActive == true {
            plan = .pro
        } else if let expiration = entitlement?.expirationDate,
                  expiration > Date() {
            plan = .grace
        } else {
            plan = .free
        }

        let productId = entitlement?.productIdentifier
        let offering = AppState.shared.cachedOffering
        let package = offering?
            .availablePackages
            .first(where: { $0.storeProduct.productIdentifier == productId })

        let mappedName: String? = {
            switch productId {
            case "ai.anicca.app.ios.monthly":
                return NSLocalizedString("subscription_plan_monthly", comment: "")
            default:
                return nil
            }
        }()

        let willRenew = entitlement?.willRenew ?? false
        // 2026-06-23: 買い切り(lifetime)は willRenew=false でも有効なので "active" 扱い
        let isLifetime = productId == "ai.anicca.app.ios.lifetime"
        let isTrial = entitlement?.periodType == .trial
        let statusString: String
        if entitlement?.isActive == true {
            statusString = isTrial ? "trialing" : (willRenew || isLifetime ? "active" : "canceled")
        } else {
            statusString = "expired"
        }
        self.init(
            plan: plan,
            status: statusString,
            currentPeriodEnd: entitlement?.expirationDate,
            managementURL: info.managementURL,
            lastSyncedAt: .now,
            productIdentifier: productId,
            // OS言語に合わせたローカライズを優先（4.0対策: アプリの現在のローカライズに合わせる）
            // mappedNameはNSLocalizedStringでOS言語に応じて適切に翻訳される
            planDisplayName: mappedName ?? package?.storeProduct.localizedTitle,
            priceDescription: package?.localizedPriceString,
            monthlyUsageLimit: nil,
            monthlyUsageRemaining: nil,
            monthlyUsageCount: nil,
            willRenew: willRenew
        )
    }
}
