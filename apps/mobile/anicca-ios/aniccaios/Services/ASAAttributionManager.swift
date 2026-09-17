import Foundation
import AdServices
import Mixpanel
import OSLog

/// Apple Search Ads Attribution Manager
/// Jake Mor #51: "Send keyword attribution to Mixpanel"
@MainActor
final class ASAAttributionManager {
    static let shared = ASAAttributionManager()
    private let logger = Logger(subsystem: "com.anicca.ios", category: "ASAAttribution")

    private let hasCheckedKey = "asa_attribution_checked"

    private init() {}

    /// 初回起動時にASAアトリビューションを取得してMixpanelに送信
    /// AppDelegate.didFinishLaunchingWithOptionsから呼び出す
    func fetchAttributionIfNeeded() async {
        // 既にチェック済みなら何もしない（初回のみ実行）
        guard !UserDefaults.standard.bool(forKey: hasCheckedKey) else {
            logger.debug("ASA attribution already checked, skipping")
            return
        }

        // チェック済みフラグを立てる（次回以降スキップ）
        UserDefaults.standard.set(true, forKey: hasCheckedKey)

        do {
            // Step 1: AdServicesからトークンを取得
            let token = try AAAttribution.attributionToken()
            logger.info("ASA attribution token obtained")

            // Step 2: AppleのAPIにトークンを送信してattribution情報を取得
            let attribution = try await fetchAttributionData(token: token)

            // Step 3: Mixpanelにユーザープロパティとして設定
            setMixpanelProperties(attribution: attribution)

        } catch {
            // ASA経由でないインストール（Organic）の場合はエラーになる
            // これは正常な挙動なのでdebugログのみ
            logger.debug("ASA attribution not available: \(error.localizedDescription)")

            // Organicインストールとしてマーク
            AnalyticsManager.shared.setUserProperty("asa_attribution", value: false)
        }
    }

    /// AppleのAttribution APIにトークンを送信
    private func fetchAttributionData(token: String) async throws -> ASAAttributionData {
        guard let url = URL(string: "https://api-adservices.apple.com/api/v1/") else {
            throw ASAError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("text/plain", forHTTPHeaderField: "Content-Type")
        request.httpBody = token.data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw ASAError.invalidResponse
        }

        let attribution = try JSONDecoder().decode(ASAAttributionData.self, from: data)
        logger.info("ASA attribution data received: campaign=\(String(describing: attribution.campaignId)), keyword=\(String(describing: attribution.keywordId))")

        return attribution
    }

    /// Mixpanelにattributionデータを設定
    private func setMixpanelProperties(attribution: ASAAttributionData) {
        var properties: [String: MixpanelType] = [
            "asa_attribution": attribution.attribution
        ]

        if let campaignId = attribution.campaignId {
            properties["asa_campaign_id"] = campaignId
        }
        if let adGroupId = attribution.adGroupId {
            properties["asa_ad_group_id"] = adGroupId
        }
        if let keywordId = attribution.keywordId {
            properties["asa_keyword_id"] = keywordId
        }
        if let countryOrRegion = attribution.countryOrRegion {
            properties["asa_country"] = countryOrRegion
        }
        if let conversionType = attribution.conversionType {
            properties["asa_conversion_type"] = conversionType
        }
        if let claimType = attribution.claimType {
            properties["asa_claim_type"] = claimType
        }
        if let adId = attribution.adId {
            properties["asa_ad_id"] = adId
        }

        AnalyticsManager.shared.setUserProperties(properties)
        logger.info("ASA attribution properties set in Mixpanel")
    }
}

// MARK: - Data Models

struct ASAAttributionData: Codable {
    let attribution: Bool
    let orgId: Int?
    let campaignId: Int?
    let conversionType: String?
    let clickDate: String?
    let impressionDate: String?
    let claimType: String?
    let adGroupId: Int?
    let countryOrRegion: String?
    let keywordId: Int?
    let adId: Int?
}

enum ASAError: Error {
    case invalidURL
    case invalidResponse
    case decodingFailed
}
