// PaywallE2ETests.swift
// 2026-06-23: ハードペイウォール E2E（StoreKit Configuration でログイン不要・無料購入）。
// `--screenshot-paywall` で paywall 直行 → スクショ → 購入 → 解錠検証。
// Test action の StoreKitConfigurationFileReference (Anicca.storekit) により simulator でサインイン不要。

import XCTest

final class PaywallE2ETests: XCTestCase {

    override func setUpWithError() throws {
        continueAfterFailure = false
        // 通知許可・StoreKit 確認などのシステムダイアログを自動処理
        addUIInterruptionMonitor(withDescription: "System dialogs") { alert in
            let titles = ["Allow", "許可", "App の使用中は許可", "OK",
                          "Subscribe", "Confirm", "Buy", "購入", "確認", "購入する",
                          "Continue", "Done", "Not Now", "今はしない"]
            for t in titles where alert.buttons[t].exists {
                alert.buttons[t].tap()
                return true
            }
            return false
        }
    }

    private func launchPaywall(lang: String, locale: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--screenshot-paywall",
                               "-AppleLanguages", "(\(lang))",
                               "-AppleLocale", locale]
        app.launch()
        return app
    }

    private func snap(_ name: String) {
        let s = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        s.name = name
        s.lifetime = .keepAlways
        add(s)
    }

    /// primer → PaywallVariantBView（paywall-plan-cta が出るまで）
    @discardableResult
    private func gotoPaywall(_ app: XCUIApplication) -> Bool {
        let primer = app.buttons["paywall-primer-cta"]
        if primer.waitForExistence(timeout: 25) { primer.tap() }
        return app.buttons["paywall-plan-cta"].waitForExistence(timeout: 25)
    }

    @MainActor
    func testPaywallScreenshotEN() throws {
        let app = launchPaywall(lang: "en", locale: "en_US")
        XCTAssertTrue(gotoPaywall(app), "EN paywall not reached")
        snap("paywall-EN")
        // no-trial: トライアルバッジが無い
        XCTAssertFalse(app.staticTexts["3 DAYS FREE"].exists, "trial badge must be gone")
    }

    @MainActor
    func testPaywallScreenshotJA() throws {
        let app = launchPaywall(lang: "ja", locale: "ja_JP")
        XCTAssertTrue(gotoPaywall(app), "JA paywall not reached")
        snap("paywall-JA")
        XCTAssertFalse(app.staticTexts["3日間無料"].exists, "trial badge must be gone")
    }

    /// ★ ハードペイウォール突破: 購入 → 解錠 ★
    @MainActor
    func testPurchaseUnlocksApp() throws {
        let app = launchPaywall(lang: "en", locale: "en_US")
        XCTAssertTrue(gotoPaywall(app), "paywall not reached")
        snap("before-purchase")

        // CTA（既定=年額選択）をタップ → StoreKit ローカル購入シート
        app.buttons["paywall-plan-cta"].tap()

        // 解錠まで「購入/確認/リテンションAccept」系ボタンを叩き続ける堅牢ループ。
        // StoreKit シート確認 + リテンション(Accept Offer) + paywall CTA 再タップを全部試す。
        let mypath = app.otherElements["mypath-root"]
        let sb = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let confirmTitles = ["Subscribe", "Confirm", "購入する", "購入", "Buy", "確認",
                             "Accept Offer", "オファーを受ける", "paywall-plan-cta"]
        var unlocked = false
        for _ in 0..<35 {
            if mypath.exists { unlocked = true; break }
            var tapped = false
            for t in confirmTitles {
                let b = app.buttons[t]
                if b.exists && b.isHittable { b.tap(); tapped = true; break }
                let s = sb.buttons[t]
                if s.exists && s.isHittable { s.tap(); tapped = true; break }
            }
            if !tapped { app.tap() } // interruption monitor 発火
            sleep(1)
        }
        unlocked = unlocked || mypath.waitForExistence(timeout: 10)
        snap("after-purchase")
        XCTAssertTrue(unlocked, "entitlement not unlocked after purchase (hard paywall not passed)")
    }

    /// Dais 最終チェック用: 英語・最初(onboarding)からアプリを起動し長時間保持（手動ウォークスルー）
    @MainActor
    func testManualWalkthrough() throws {
        let app = XCUIApplication()
        app.launchArguments = ["-resetOnLaunch", "-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
        sleep(1500) // 25分: Dais が最初から英語で全画面を手動確認
    }
}
