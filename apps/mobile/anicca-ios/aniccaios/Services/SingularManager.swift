import Foundation
import UIKit
import OSLog

@MainActor
final class SingularManager {
    static let shared = SingularManager()
    private let logger = Logger(subsystem: "com.anicca.ios", category: "Singular")
    private var isConfigured = false

    private init() {}

    func configure(launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) {
        guard !isConfigured else { return }

        guard let apiKey = Bundle.main.object(forInfoDictionaryKey: "SINGULAR_API_KEY") as? String,
              let secret = Bundle.main.object(forInfoDictionaryKey: "SINGULAR_SECRET") as? String,
              !apiKey.isEmpty, !secret.isEmpty,
              let config = SingularConfig(apiKey: apiKey, andSecret: secret) else {
            logger.error("Singular private build configuration is missing")
            return
        }

        // ATT なし: waitForTrackingAuthorization は設定しない
        // SKAN は SDK 12.0.6+ で自動有効（Singular Dashboard で Managed Mode）
        config.launchOptions = launchOptions
        config.skAdNetworkEnabled = true
        config.enableLogging = true

        Singular.start(config)
        isConfigured = true
        logger.info("Singular SDK initialized (IDFV + SKAN, no ATT)")
    }
}
