// aniccaios/aniccaiosTests/SingleScreenTests.swift

import Testing
@testable import aniccaios

@Suite("Single Screen Tests")
struct SingleScreenTests {

    // MARK: - Subscription Display Condition Tests

    @Test("shouldShowSubscribeButton returns true for free plan")
    func test_should_show_subscribe_for_free() {
        #expect(SingleScreenDisplayConditions.shouldShowSubscribeButton(plan: .free) == true)
    }

    @Test("shouldShowSubscribeButton returns false for pro plan")
    func test_should_show_subscribe_for_pro() {
        #expect(SingleScreenDisplayConditions.shouldShowSubscribeButton(plan: .pro) == false)
    }

    @Test("shouldShowCancelSubscriptionButton returns true for pro plan")
    func test_should_show_cancel_for_pro() {
        #expect(SingleScreenDisplayConditions.shouldShowCancelSubscriptionButton(plan: .pro) == true)
    }

    @Test("shouldShowCancelSubscriptionButton returns false for free plan")
    func test_should_show_cancel_for_free() {
        #expect(SingleScreenDisplayConditions.shouldShowCancelSubscriptionButton(plan: .free) == false)
    }

    // MARK: - Account Display Condition Tests

    @Test("shouldShowSignOutButton returns true when signed in")
    func test_should_show_sign_out_when_signed_in() {
        #expect(SingleScreenDisplayConditions.shouldShowSignOutButton(isSignedIn: true) == true)
    }

    @Test("shouldShowSignOutButton returns false when not signed in")
    func test_should_show_sign_out_when_not_signed_in() {
        #expect(SingleScreenDisplayConditions.shouldShowSignOutButton(isSignedIn: false) == false)
    }

    @Test("shouldShowDeleteAccountButton returns true when signed in")
    func test_should_show_delete_account_when_signed_in() {
        #expect(SingleScreenDisplayConditions.shouldShowDeleteAccountButton(isSignedIn: true) == true)
    }

    @Test("shouldShowDeleteAccountButton returns false when not signed in")
    func test_should_show_delete_account_when_not_signed_in() {
        #expect(SingleScreenDisplayConditions.shouldShowDeleteAccountButton(isSignedIn: false) == false)
    }

    // MARK: - Migration Tests（migrateFromAlarmKit直接テスト + Mock Scheduler）

    @Test("migrateFromAlarmKit sets flag and calls scheduler")
    func test_migrate_from_alarmkit_calls_scheduler() async {
        let migrationKey = "alarmKitMigrationCompleted_v1_3_0"
        UserDefaults.standard.removeObject(forKey: migrationKey)

        // Mock Scheduler を使用して呼び出しを検証
        let mockScheduler = MockProblemNotificationScheduler()

        // 移行前
        #expect(UserDefaults.standard.bool(forKey: migrationKey) == false)
        #expect(mockScheduler.scheduleNotificationsCalled == false)

        // migrateFromAlarmKit() を直接呼び出し（Mock注入版、cant_wake_up含む問題リスト）
        let testProblems = ["cant_wake_up", "staying_up_late"]
        await migrateFromAlarmKitTestable(scheduler: mockScheduler, problems: testProblems)

        // 移行後: フラグが設定され、Schedulerが呼ばれたことを確認
        #expect(UserDefaults.standard.bool(forKey: migrationKey) == true)
        #expect(mockScheduler.scheduleNotificationsCalled == true)

        // クリーンアップ
        UserDefaults.standard.removeObject(forKey: migrationKey)
    }

    @Test("migrateFromAlarmKit schedules correct problems including cant_wake_up")
    func test_migrate_from_alarmkit_schedules_correct_problems() async {
        let migrationKey = "alarmKitMigrationCompleted_v1_3_0"
        UserDefaults.standard.removeObject(forKey: migrationKey)

        let mockScheduler = MockProblemNotificationScheduler()
        let testProblems = ["cant_wake_up", "staying_up_late", "procrastination"]

        await migrateFromAlarmKitTestable(scheduler: mockScheduler, problems: testProblems)

        // 問題リストが正しく渡されたか検証
        #expect(mockScheduler.scheduledProblems == testProblems)
        #expect(mockScheduler.scheduledProblems.contains("cant_wake_up") == true)

        // クリーンアップ
        UserDefaults.standard.removeObject(forKey: migrationKey)
    }

    @Test("cant_wake_up is scheduled in migration")
    func test_cant_wake_up_scheduled_in_migration() async {
        let migrationKey = "alarmKitMigrationCompleted_v1_3_0"
        UserDefaults.standard.removeObject(forKey: migrationKey)

        let mockScheduler = MockProblemNotificationScheduler()
        let testProblems = ["cant_wake_up"]

        await migrateFromAlarmKitTestable(scheduler: mockScheduler, problems: testProblems)

        // cant_wake_up が通知スケジュール対象に含まれていることを確認
        #expect(mockScheduler.scheduledProblems.contains("cant_wake_up") == true)

        // クリーンアップ
        UserDefaults.standard.removeObject(forKey: migrationKey)
    }

    @Test("migrateFromAlarmKit skipped if already completed")
    func test_migrate_from_alarmkit_skipped_if_completed() async {
        let migrationKey = "alarmKitMigrationCompleted_v1_3_0"

        // 移行完了済みをシミュレート
        UserDefaults.standard.set(true, forKey: migrationKey)

        let mockScheduler = MockProblemNotificationScheduler()

        // migrateFromAlarmKit() を呼び出し
        await migrateFromAlarmKitTestable(scheduler: mockScheduler, problems: ["cant_wake_up"])

        // Schedulerは呼ばれない（early return）
        #expect(mockScheduler.scheduleNotificationsCalled == false)

        // クリーンアップ
        UserDefaults.standard.removeObject(forKey: migrationKey)
    }
}

// MARK: - Test Helpers

/// テスト用 Mock Scheduler
class MockProblemNotificationScheduler: ProblemNotificationSchedulerProtocol {
    var scheduleNotificationsCalled = false
    var scheduledProblems: [String] = []

    func scheduleNotifications(for problems: [String]) async {
        scheduleNotificationsCalled = true
        scheduledProblems = problems
    }
}
