// UITests/ScreenshotTests.swift
// l.md Bible Step 2: XCTAttachment でスクリーンショット撮影

import XCTest

final class ScreenshotTests: XCTestCase {

    override func setUpWithError() throws {
        continueAfterFailure = false

        // システムアラート（通知許可など）を自動で処理
        addUIInterruptionMonitor(withDescription: "System Alert") { alert in
            let allowButtons = ["Allow", "許可", "OK", "開く", "Open", "キャンセル"]
            for title in allowButtons {
                if alert.buttons[title].exists {
                    alert.buttons[title].tap()
                    return true
                }
            }
            return false
        }
    }

    @MainActor
    func testCaptureScreen1() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--screenshot-screen1"]
        app.launch()

        sleep(5)
        // InterruptionMonitorを発火させるためにタップ（l.md: システムアラート自動処理）
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)

        takeScreenshot(named: "screen1")
    }

    @MainActor
    func testCaptureScreen2() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--screenshot-screen2"]
        app.launch()

        sleep(5)
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)

        takeScreenshot(named: "screen2")
    }

    @MainActor
    func testCaptureScreen3() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--screenshot-screen3"]
        app.launch()

        sleep(5)
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)

        takeScreenshot(named: "screen3")
    }

    // 標準機能だけで撮影するヘルパー（l.md Bible: SnapshotHelper不使用）
    private func takeScreenshot(named name: String) {
        let screenshot = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        // これが重要！デフォルトは成功時に削除されてしまう
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
