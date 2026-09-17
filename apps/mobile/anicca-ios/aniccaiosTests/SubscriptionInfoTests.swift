// SubscriptionInfoTests.swift
// Hard Paywall + Monthly + Free Trial - Unit Tests
// TDD: RED Phase

import XCTest
@testable import aniccaios

final class SubscriptionInfoTests: XCTestCase {

    // MARK: - isActiveSubscriber Tests

    func test_isActiveSubscriber_whenActive_returnsTrue() {
        let info = SubscriptionInfo(
            plan: .pro,
            status: "active",
            currentPeriodEnd: nil,
            managementURL: nil,
            lastSyncedAt: .now,
            productIdentifier: nil,
            planDisplayName: nil,
            priceDescription: nil,
            monthlyUsageLimit: nil,
            monthlyUsageRemaining: nil,
            monthlyUsageCount: nil,
            willRenew: true
        )
        XCTAssertTrue(info.isActiveSubscriber)
    }

    func test_isActiveSubscriber_whenTrialing_returnsTrue() {
        let info = SubscriptionInfo(
            plan: .pro,
            status: "trialing",
            currentPeriodEnd: nil,
            managementURL: nil,
            lastSyncedAt: .now,
            productIdentifier: nil,
            planDisplayName: nil,
            priceDescription: nil,
            monthlyUsageLimit: nil,
            monthlyUsageRemaining: nil,
            monthlyUsageCount: nil,
            willRenew: true
        )
        XCTAssertTrue(info.isActiveSubscriber)
    }

    func test_isActiveSubscriber_whenCanceled_returnsFalse() {
        let info = SubscriptionInfo(
            plan: .pro,
            status: "canceled",
            currentPeriodEnd: nil,
            managementURL: nil,
            lastSyncedAt: .now,
            productIdentifier: nil,
            planDisplayName: nil,
            priceDescription: nil,
            monthlyUsageLimit: nil,
            monthlyUsageRemaining: nil,
            monthlyUsageCount: nil,
            willRenew: false
        )
        XCTAssertFalse(info.isActiveSubscriber)
    }

    func test_isActiveSubscriber_whenProExpired_returnsFalse() {
        // plan=.pro でも status="expired" ならブロック
        let info = SubscriptionInfo(
            plan: .pro,
            status: "expired",
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
        XCTAssertFalse(info.isActiveSubscriber)
    }

    func test_isActiveSubscriber_whenProUnknownStatus_returnsFalse() {
        // fail-close: 未知のステータスはブロック
        let info = SubscriptionInfo(
            plan: .pro,
            status: "some_unknown_status",
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
        XCTAssertFalse(info.isActiveSubscriber)
    }

    func test_isActiveSubscriber_whenGracePlanWithGraceStatus_returnsTrue() {
        let info = SubscriptionInfo(
            plan: .grace,
            status: "grace",
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
        XCTAssertTrue(info.isActiveSubscriber)
    }

    func test_isActiveSubscriber_whenGracePlanWithExpiredStatus_returnsFalse() {
        // fail-close: .grace でも status が allowlist 外ならブロック
        let info = SubscriptionInfo(
            plan: .grace,
            status: "expired",
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
        XCTAssertFalse(info.isActiveSubscriber)
    }

    func test_isActiveSubscriber_whenProWithGraceStatus_returnsTrue() {
        // 後方互換: plan=.pro, status=in_grace_period のケース
        let info = SubscriptionInfo(
            plan: .pro,
            status: "in_grace_period",
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
        XCTAssertTrue(info.isActiveSubscriber)
    }

    // MARK: - isSubscriptionExpiredOrCanceled Tests

    func test_isExpiredOrCanceled_whenExpired_returnsTrue() {
        let info = SubscriptionInfo(
            plan: .pro,
            status: "expired",
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
        XCTAssertTrue(info.isSubscriptionExpiredOrCanceled)
    }

    func test_isExpiredOrCanceled_whenFree_returnsTrue() {
        let info = SubscriptionInfo.free
        XCTAssertTrue(info.isSubscriptionExpiredOrCanceled)
    }

    func test_isExpiredOrCanceled_whenCanceled_returnsTrue() {
        let info = SubscriptionInfo(
            plan: .pro,
            status: "canceled",
            currentPeriodEnd: nil,
            managementURL: nil,
            lastSyncedAt: .now,
            productIdentifier: nil,
            planDisplayName: nil,
            priceDescription: nil,
            monthlyUsageLimit: nil,
            monthlyUsageRemaining: nil,
            monthlyUsageCount: nil,
            willRenew: false
        )
        XCTAssertTrue(info.isSubscriptionExpiredOrCanceled)
    }

    func test_isExpiredOrCanceled_whenActive_returnsFalse() {
        let info = SubscriptionInfo(
            plan: .pro,
            status: "active",
            currentPeriodEnd: nil,
            managementURL: nil,
            lastSyncedAt: .now,
            productIdentifier: nil,
            planDisplayName: nil,
            priceDescription: nil,
            monthlyUsageLimit: nil,
            monthlyUsageRemaining: nil,
            monthlyUsageCount: nil,
            willRenew: true
        )
        XCTAssertFalse(info.isSubscriptionExpiredOrCanceled)
    }

    func test_isExpiredOrCanceled_whenTrialing_returnsFalse() {
        let info = SubscriptionInfo(
            plan: .pro,
            status: "trialing",
            currentPeriodEnd: nil,
            managementURL: nil,
            lastSyncedAt: .now,
            productIdentifier: nil,
            planDisplayName: nil,
            priceDescription: nil,
            monthlyUsageLimit: nil,
            monthlyUsageRemaining: nil,
            monthlyUsageCount: nil,
            willRenew: true
        )
        XCTAssertFalse(info.isSubscriptionExpiredOrCanceled)
    }

    func test_isExpiredOrCanceled_whenGracePlanWithGraceStatus_returnsFalse() {
        let info = SubscriptionInfo(
            plan: .grace,
            status: "grace",
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
        XCTAssertFalse(info.isSubscriptionExpiredOrCanceled)
    }

    func test_isExpiredOrCanceled_whenProWithGraceStatus_returnsFalse() {
        // 後方互換: plan=.pro, status=billing_issue のケース
        let info = SubscriptionInfo(
            plan: .pro,
            status: "billing_issue",
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
        XCTAssertFalse(info.isSubscriptionExpiredOrCanceled)
    }

    func test_isExpiredOrCanceled_whenFreeWithGraceStatus_returnsTrue() {
        // セキュリティ: plan=.free は status に関わらず常にブロック
        let info = SubscriptionInfo(
            plan: .free,
            status: "billing_issue",  // grace 系ステータスでも free ならブロック
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
        XCTAssertTrue(info.isSubscriptionExpiredOrCanceled)
    }
}
