import Foundation
import OSLog

/// LLM生成NudgeのAPI呼び出しサービス
actor LLMNudgeService {
    static let shared = LLMNudgeService()

    private let logger = Logger(subsystem: "com.anicca.ios", category: "LLMNudgeService")
    private let session: URLSession
    private let decoder: JSONDecoder

    /// 今日の戦略（LLMが生成）- Phase 7+8
    private(set) var overallStrategy: String?

    private init() {
        self.session = URLSession.shared
        self.decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601  // ISO8601文字列をDateに変換
    }

    /// 今日生成されたNudgeを取得
    func fetchTodaysNudges() async throws -> [LLMGeneratedNudge] {
        // Free ユーザーは LLM Nudge 無効（APIコスト節約）
        let isEntitled = await MainActor.run { AppState.shared.subscriptionInfo.isEntitled }
        guard isEntitled else {
            logger.info("ℹ️ [LLM] Free user, skipping LLM fetch")
            return []
        }

        let (url, appVersion) = await MainActor.run { (AppConfig.nudgeTodayURL, AppConfig.appVersion) }
        let deviceId = await AppState.shared.resolveDeviceId()
        logger.info("🔄 [LLM] Requesting: \(url.absoluteString) with deviceId: \(deviceId), v\(appVersion)")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(deviceId, forHTTPHeaderField: "device-id")
        request.setValue(deviceId, forHTTPHeaderField: "user-id")
        // v1.6.0: Send app version for schedule map selection
        request.setValue(appVersion, forHTTPHeaderField: "X-App-Version")

        do {
            let (data, response) = try await session.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw ServiceError.invalidResponse
            }

            guard (200..<300).contains(httpResponse.statusCode) else {
                logger.error("❌ [LLM] Failed: HTTP \(httpResponse.statusCode)")
                if let body = String(data: data, encoding: .utf8) {
                    logger.error("❌ [LLM] Response: \(body)")
                }
                throw ServiceError.httpError(httpResponse.statusCode)
            }

            let responseBody: NudgeTodayResponse
            do {
                responseBody = try decoder.decode(NudgeTodayResponse.self, from: data)
            } catch {
                logger.error("❌ [LLM] Decode error: \(error.localizedDescription)")
                throw error
            }

            // Phase 7+8: overallStrategyを保存
            self.overallStrategy = responseBody.overallStrategy

            logger.info("✅ [LLM] Decoded \(responseBody.nudges.count) nudges, strategy: \(responseBody.overallStrategy ?? "none")")
            return responseBody.nudges
        } catch {
            logger.error("Failed to fetch todays nudges: \(error.localizedDescription)")
            throw error
        }
    }

    enum ServiceError: Error {
        case invalidResponse
        case httpError(Int)
    }
}

/// APIレスポンス形式（Phase 7+8拡張版）
private struct NudgeTodayResponse: Codable {
    let nudges: [LLMGeneratedNudge]
    let overallStrategy: String?  // Phase 7+8: LLMが生成した今日の戦略
    let version: String?          // APIバージョン（後方互換確認用）
}
