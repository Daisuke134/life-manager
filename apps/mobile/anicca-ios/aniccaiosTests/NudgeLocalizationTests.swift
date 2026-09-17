import XCTest
@testable import aniccaios

/// v1.5.1: EN/JA ローカリゼーション完全性テスト
/// 全13問題タイプ × 全バリアント × notification/detail × EN/JA
final class NudgeLocalizationTests: XCTestCase {

    // MARK: - Helper

    /// 問題タイプの rawValue → ローカリゼーションキーのプレフィックス
    private func localizationPrefix(for problem: ProblemType) -> String {
        return problem.rawValue.replacingOccurrences(of: "-", with: "_")
    }

    /// 指定ロケールのBundleを取得（アプリbundleからlprojを探す）
    private func bundle(for locale: String) -> Bundle? {
        // Hosted tests: Bundle.main = host app bundle containing lproj resources
        guard let path = Bundle.main.path(forResource: locale, ofType: "lproj") else {
            return nil
        }
        return Bundle(path: path)
    }

    /// キーがローカライズされているか検証（キーそのものが返ってきたら未翻訳）
    private func assertLocalized(
        key: String,
        bundle: Bundle,
        locale: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        let value = NSLocalizedString(key, tableName: nil, bundle: bundle, value: "##MISSING##", comment: "")
        XCTAssertNotEqual(value, "##MISSING##", "\(locale): Missing key '\(key)'", file: file, line: line)
        XCTAssertNotEqual(value, key, "\(locale): Key '\(key)' returned itself (not localized)", file: file, line: line)
        XCTAssertFalse(value.isEmpty, "\(locale): Key '\(key)' is empty", file: file, line: line)
    }

    // MARK: - EN Localization Tests

    /// 全問題タイプの通知文言が英語で存在すること
    func test_allNotificationMessages_existInEN() {
        guard let enBundle = bundle(for: "en") else {
            XCTFail("EN bundle not found")
            return
        }

        for problem in ProblemType.allCases {
            let prefix = localizationPrefix(for: problem)
            let variantCount = problem.notificationVariantCount

            for i in 1...variantCount {
                let key = "nudge_\(prefix)_notification_\(i)"
                assertLocalized(key: key, bundle: enBundle, locale: "EN")
            }
        }
    }

    /// 全問題タイプの詳細文言が英語で存在すること
    func test_allDetailMessages_existInEN() {
        guard let enBundle = bundle(for: "en") else {
            XCTFail("EN bundle not found")
            return
        }

        for problem in ProblemType.allCases {
            let prefix = localizationPrefix(for: problem)
            let variantCount = problem.notificationVariantCount

            for i in 1...variantCount {
                let key = "nudge_\(prefix)_detail_\(i)"
                assertLocalized(key: key, bundle: enBundle, locale: "EN")
            }
        }
    }

    // MARK: - JA Localization Tests

    /// 全問題タイプの通知文言が日本語で存在すること
    func test_allNotificationMessages_existInJA() {
        guard let jaBundle = bundle(for: "ja") else {
            XCTFail("JA bundle not found")
            return
        }

        for problem in ProblemType.allCases {
            let prefix = localizationPrefix(for: problem)
            let variantCount = problem.notificationVariantCount

            for i in 1...variantCount {
                let key = "nudge_\(prefix)_notification_\(i)"
                assertLocalized(key: key, bundle: jaBundle, locale: "JA")
            }
        }
    }

    /// 全問題タイプの詳細文言が日本語で存在すること
    func test_allDetailMessages_existInJA() {
        guard let jaBundle = bundle(for: "ja") else {
            XCTFail("JA bundle not found")
            return
        }

        for problem in ProblemType.allCases {
            let prefix = localizationPrefix(for: problem)
            let variantCount = problem.notificationVariantCount

            for i in 1...variantCount {
                let key = "nudge_\(prefix)_detail_\(i)"
                assertLocalized(key: key, bundle: jaBundle, locale: "JA")
            }
        }
    }

    // MARK: - Variant Count Consistency

    /// NudgeContent.notificationMessages の配列長が notificationVariantCount と一致すること
    func test_notificationMessages_countMatchesVariantCount() {
        for problem in ProblemType.allCases {
            let messages = NudgeContent.notificationMessages(for: problem)
            XCTAssertEqual(
                messages.count,
                problem.notificationVariantCount,
                "\(problem.rawValue): notificationMessages count (\(messages.count)) != notificationVariantCount (\(problem.notificationVariantCount))"
            )
        }
    }

    /// NudgeContent.detailMessages の配列長が notificationVariantCount と一致すること
    func test_detailMessages_countMatchesVariantCount() {
        for problem in ProblemType.allCases {
            let details = NudgeContent.detailMessages(for: problem)
            XCTAssertEqual(
                details.count,
                problem.notificationVariantCount,
                "\(problem.rawValue): detailMessages count (\(details.count)) != notificationVariantCount (\(problem.notificationVariantCount))"
            )
        }
    }

    // MARK: - EN/JA Parity

    /// EN と JA で同じキーが存在すること（パリティチェック）
    func test_enJaParity_allNudgeKeys() {
        guard let enBundle = bundle(for: "en"),
              let jaBundle = bundle(for: "ja") else {
            XCTFail("EN or JA bundle not found")
            return
        }

        var missingInJA: [String] = []
        var missingInEN: [String] = []

        for problem in ProblemType.allCases {
            let prefix = localizationPrefix(for: problem)
            let variantCount = problem.notificationVariantCount

            for i in 1...variantCount {
                for suffix in ["notification", "detail"] {
                    let key = "nudge_\(prefix)_\(suffix)_\(i)"

                    let enValue = NSLocalizedString(key, tableName: nil, bundle: enBundle, value: "##MISSING##", comment: "")
                    let jaValue = NSLocalizedString(key, tableName: nil, bundle: jaBundle, value: "##MISSING##", comment: "")

                    if enValue == "##MISSING##" || enValue == key {
                        missingInEN.append(key)
                    }
                    if jaValue == "##MISSING##" || jaValue == key {
                        missingInJA.append(key)
                    }
                }
            }
        }

        XCTAssertTrue(missingInEN.isEmpty, "Missing in EN: \(missingInEN.joined(separator: ", "))")
        XCTAssertTrue(missingInJA.isEmpty, "Missing in JA: \(missingInJA.joined(separator: ", "))")
    }

    // MARK: - Content Quality

    /// 通知文言が空でなく適切な長さであること（EN）
    func test_notificationMessages_haveReasonableLength_EN() {
        guard let enBundle = bundle(for: "en") else {
            XCTFail("EN bundle not found")
            return
        }

        for problem in ProblemType.allCases {
            let prefix = localizationPrefix(for: problem)

            for i in 1...problem.notificationVariantCount {
                let key = "nudge_\(prefix)_notification_\(i)"
                let value = NSLocalizedString(key, tableName: nil, bundle: enBundle, value: "", comment: "")

                // 通知は短い（5-100文字程度）
                XCTAssertGreaterThan(value.count, 3,
                    "EN \(key) too short (\(value.count) chars): '\(value)'")
                XCTAssertLessThan(value.count, 120,
                    "EN \(key) too long (\(value.count) chars)")
            }
        }
    }

    /// 詳細文言が空でなく適切な長さであること（EN）
    func test_detailMessages_haveReasonableLength_EN() {
        guard let enBundle = bundle(for: "en") else {
            XCTFail("EN bundle not found")
            return
        }

        for problem in ProblemType.allCases {
            let prefix = localizationPrefix(for: problem)

            for i in 1...problem.notificationVariantCount {
                let key = "nudge_\(prefix)_detail_\(i)"
                let value = NSLocalizedString(key, tableName: nil, bundle: enBundle, value: "", comment: "")

                // 詳細は長め（20-500文字程度）
                XCTAssertGreaterThan(value.count, 10,
                    "EN \(key) too short (\(value.count) chars): '\(value)'")
            }
        }
    }
}
