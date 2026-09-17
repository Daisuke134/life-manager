import Foundation

struct SubscriptionInfo: Codable, Equatable {
    enum Plan: String, Codable { case free, grace, pro }
    var plan: Plan
    var status: String
    var currentPeriodEnd: Date?
    var managementURL: URL?
    var lastSyncedAt: Date
    var productIdentifier: String?
    var planDisplayName: String?
    var priceDescription: String?
    var monthlyUsageLimit: Int?
    var monthlyUsageRemaining: Int?
    var monthlyUsageCount: Int?
    var willRenew: Bool?
    
    var isEntitled: Bool { plan != .free && status != "expired" }
    var shouldShowPaywall: Bool { !isEntitled }

    /// 課金更新に失敗し、Apple がリトライ中(grace/billing retry)の状態。
    /// アクセスはまだ継続しているが、ユーザーが支払い方法を更新しないと失効する。
    /// → involuntary churn を防ぐため、支払い更新を促す導線を出す。
    var hasBillingIssue: Bool {
        let billingStates: Set<String> = ["grace", "in_grace_period", "billing_issue", "billing_retry"]
        return billingStates.contains(status)
    }

    // MARK: - Hard Paywall Properties

    /// 許可されるステータス（fail-close: このリストにないステータスはブロック）
    private static let allowedStatuses: Set<String> = [
        "active", "trialing",
        "grace", "in_grace_period", "billing_issue", "billing_retry"
    ]

    /// アクティブなサブスクライバーかどうか（アプリ利用を許可するか）
    var isActiveSubscriber: Bool {
        return !isSubscriptionExpiredOrCanceled
    }

    /// サブスクリプションが期限切れまたはキャンセル済みか
    var isSubscriptionExpiredOrCanceled: Bool {
        // セキュリティ: plan=.free は status に関わらず常にブロック
        if plan == .free { return true }
        // fail-close: allowedStatuses にないステータスはブロック
        return !Self.allowedStatuses.contains(status)
    }

    // `init(from:)` を定義していると memberwise init が合成されないケースがあるため明示定義
    init(
        plan: Plan,
        status: String,
        currentPeriodEnd: Date?,
        managementURL: URL?,
        lastSyncedAt: Date,
        productIdentifier: String?,
        planDisplayName: String?,
        priceDescription: String?,
        monthlyUsageLimit: Int?,
        monthlyUsageRemaining: Int?,
        monthlyUsageCount: Int?,
        willRenew: Bool?
    ) {
        self.plan = plan
        self.status = status
        self.currentPeriodEnd = currentPeriodEnd
        self.managementURL = managementURL
        self.lastSyncedAt = lastSyncedAt
        self.productIdentifier = productIdentifier
        self.planDisplayName = planDisplayName
        self.priceDescription = priceDescription
        self.monthlyUsageLimit = monthlyUsageLimit
        self.monthlyUsageRemaining = monthlyUsageRemaining
        self.monthlyUsageCount = monthlyUsageCount
        self.willRenew = willRenew
    }
    
    static let free = SubscriptionInfo(
        plan: .free,
        status: "free",
        currentPeriodEnd: nil,
        managementURL: nil,
        lastSyncedAt: .now,
        productIdentifier: nil,
        planDisplayName: nil,
        priceDescription: nil,
        monthlyUsageLimit: nil,
        monthlyUsageRemaining: nil,
        monthlyUsageCount: nil,
        willRenew: nil
    )
    
    var displayPlanName: String {
        if let planDisplayName = planDisplayName, !planDisplayName.isEmpty {
            return planDisplayName
        }
        switch plan {
        case .free:
            return NSLocalizedString("settings_subscription_free", comment: "")
        case .grace:
            return NSLocalizedString("settings_subscription_grace", comment: "")
        case .pro:
            return NSLocalizedString("settings_subscription_pro", comment: "")
        }
    }
    
    // server(=snake_case) と 既存UserDefaults(=camelCase) の両方をデコードできるようにする
    private enum SnakeCodingKeys: String, CodingKey {
        case plan
        case status
        case currentPeriodEnd = "current_period_end"
        case managementURL = "management_url"
        case lastSyncedAt = "last_synced_at"
        case productIdentifier = "product_identifier"
        case planDisplayName = "plan_display_name"
        case priceDescription = "price_description"
        case monthlyUsageLimit = "monthly_usage_limit"
        case monthlyUsageRemaining = "monthly_usage_remaining"
        case monthlyUsageCount = "monthly_usage_count"
        case willRenew = "will_renew"
    }
    
    private enum LegacyCodingKeys: String, CodingKey {
        case plan
        case status
        case currentPeriodEnd
        case managementURL
        case lastSyncedAt
        case productIdentifier
        case planDisplayName
        case priceDescription
        case monthlyUsageLimit
        case monthlyUsageRemaining
        case monthlyUsageCount
        case willRenew
    }
    
    init(from decoder: Decoder) throws {
        let snake = try decoder.container(keyedBy: SnakeCodingKeys.self)
        let legacy = try decoder.container(keyedBy: LegacyCodingKeys.self)
        
        plan = try snake.decodeIfPresent(Plan.self, forKey: .plan)
            ?? legacy.decodeIfPresent(Plan.self, forKey: .plan)
            ?? .free
        status = try snake.decodeIfPresent(String.self, forKey: .status)
            ?? legacy.decodeIfPresent(String.self, forKey: .status)
            ?? "free"
        
        currentPeriodEnd = try snake.decodeIfPresent(Date.self, forKey: .currentPeriodEnd)
            ?? legacy.decodeIfPresent(Date.self, forKey: .currentPeriodEnd)
        managementURL = try snake.decodeIfPresent(URL.self, forKey: .managementURL)
            ?? legacy.decodeIfPresent(URL.self, forKey: .managementURL)
        lastSyncedAt = try snake.decodeIfPresent(Date.self, forKey: .lastSyncedAt)
            ?? legacy.decodeIfPresent(Date.self, forKey: .lastSyncedAt)
            ?? .now
        
        productIdentifier = try snake.decodeIfPresent(String.self, forKey: .productIdentifier)
            ?? legacy.decodeIfPresent(String.self, forKey: .productIdentifier)
        planDisplayName = try snake.decodeIfPresent(String.self, forKey: .planDisplayName)
            ?? legacy.decodeIfPresent(String.self, forKey: .planDisplayName)
        priceDescription = try snake.decodeIfPresent(String.self, forKey: .priceDescription)
            ?? legacy.decodeIfPresent(String.self, forKey: .priceDescription)
        
        monthlyUsageLimit = try snake.decodeIfPresent(Int.self, forKey: .monthlyUsageLimit)
            ?? legacy.decodeIfPresent(Int.self, forKey: .monthlyUsageLimit)
        monthlyUsageRemaining = try snake.decodeIfPresent(Int.self, forKey: .monthlyUsageRemaining)
            ?? legacy.decodeIfPresent(Int.self, forKey: .monthlyUsageRemaining)
        monthlyUsageCount = try snake.decodeIfPresent(Int.self, forKey: .monthlyUsageCount)
            ?? legacy.decodeIfPresent(Int.self, forKey: .monthlyUsageCount)
        willRenew = try snake.decodeIfPresent(Bool.self, forKey: .willRenew)
            ?? legacy.decodeIfPresent(Bool.self, forKey: .willRenew)
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: SnakeCodingKeys.self)
        try container.encode(plan, forKey: .plan)
        try container.encode(status, forKey: .status)
        try container.encodeIfPresent(currentPeriodEnd, forKey: .currentPeriodEnd)
        try container.encodeIfPresent(managementURL, forKey: .managementURL)
        try container.encode(lastSyncedAt, forKey: .lastSyncedAt)
        try container.encodeIfPresent(productIdentifier, forKey: .productIdentifier)
        try container.encodeIfPresent(planDisplayName, forKey: .planDisplayName)
        try container.encodeIfPresent(priceDescription, forKey: .priceDescription)
        try container.encodeIfPresent(monthlyUsageLimit, forKey: .monthlyUsageLimit)
        try container.encodeIfPresent(monthlyUsageRemaining, forKey: .monthlyUsageRemaining)
        try container.encodeIfPresent(monthlyUsageCount, forKey: .monthlyUsageCount)
        try container.encodeIfPresent(willRenew, forKey: .willRenew)
    }
}


