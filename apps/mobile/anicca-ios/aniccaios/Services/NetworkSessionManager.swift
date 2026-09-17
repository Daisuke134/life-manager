import Foundation

/// RevenueCatのHTTPClientと同様の設定を使用したURLSessionConfigurationを提供
/// ネットワーク警告（pdp_ip0）を抑制するため
@MainActor
final class NetworkSessionManager {
    static let shared = NetworkSessionManager()

    #if DEBUG
    /// Test hook: allow unit tests to inject a custom URLSession (e.g., with URLProtocol stubs).
    static var testSession: URLSession? = nil
    #endif
    
    private let sessionConfiguration: URLSessionConfiguration
    
    private init() {
        // RevenueCatのHTTPClient.swiftと同様の設定
        let config = URLSessionConfiguration.ephemeral
        config.httpMaximumConnectionsPerHost = 4
        config.timeoutIntervalForRequest = 8.0
        config.timeoutIntervalForResource = 30.0
        config.urlCache = nil // キャッシュは使用しない
        // multipathServiceTypeは設定しない（公式実装に合わせる）
        self.sessionConfiguration = config
    }
    
    /// 専用URLSessionを返す
    var session: URLSession {
        #if DEBUG
        if let s = Self.testSession { return s }
        #endif
        return URLSession(configuration: sessionConfiguration)
    }
}

// MARK: - Auth helpers
extension NetworkSessionManager {
    enum AuthError: Error {
        case notAuthenticated
    }
    
    @MainActor
    func setAuthHeaders(for request: inout URLRequest) async throws {
        guard case .signedIn(let credentials) = AppState.shared.authStatus else {
            throw AuthError.notAuthenticated
        }
        if let exp = credentials.accessTokenExpiresAt, exp.addingTimeInterval(-60) <= Date() {
            try await refreshIfNeeded()
        }
        if let at = (AppState.shared.authStatus).accessToken {
            request.setValue("Bearer \(at)", forHTTPHeaderField: "Authorization")
        } else if let at = credentials.jwtAccessToken {
            request.setValue("Bearer \(at)", forHTTPHeaderField: "Authorization")
        }
    }
    
    private func refreshIfNeeded() async throws {
        guard let rtData = KeychainService.load(account: "rt"),
              let rt = String(data: rtData, encoding: .utf8),
              !rt.isEmpty else { return }
        var req = URLRequest(url: AppConfig.proxyBaseURL.appendingPathComponent("auth/refresh"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["refresh_token": rt])
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode),
              let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        let newAT = json["token"] as? String
        let expMs = json["expiresAt"] as? TimeInterval
        let newRT = json["refreshToken"] as? String
        if let newRT = newRT {
            try? KeychainService.save(Data(newRT.utf8), account: "rt")
        }
        await MainActor.run {
            AppState.shared.updateAccessToken(token: newAT, expiresAtMs: expMs)
        }
    }
}

// MARK: - v0.3 API Error normalization
/// serverの共通エラーフォーマット（`{"error":{"code","message","details"}}`）に合わせた iOS 側の標準エラー。
enum AniccaAPIError: Error, LocalizedError {
    case invalidRequest(message: String)
    case unauthorized
    case quotaExceeded
    case forbidden
    case notFound
    case validationError(message: String, details: [String: Any])
    case rateLimited
    case serviceUnavailable
    case serverError(message: String)
    
    var errorDescription: String? {
        switch self {
        case .invalidRequest(let message): return message
        case .unauthorized: return "UNAUTHORIZED"
        case .quotaExceeded: return "QUOTA_EXCEEDED"
        case .forbidden: return "FORBIDDEN"
        case .notFound: return "NOT_FOUND"
        case .validationError(let message, _): return message.isEmpty ? "VALIDATION_ERROR" : message
        case .rateLimited: return "RATE_LIMITED"
        case .serviceUnavailable: return "SERVICE_UNAVAILABLE"
        case .serverError(let message): return message.isEmpty ? "INTERNAL_ERROR" : message
        }
    }
    
    /// `migration-patch-v3.md 7.3` のマッピングをベースに、statusCode と body から正規化する。
    static func from(statusCode: Int, data: Data) -> AniccaAPIError {
        let parsed = NetworkSessionManager.parseErrorPayload(data)
        let message = parsed.message
        let details = parsed.details
        
        switch statusCode {
        case 400: return .invalidRequest(message: message)
        case 401: return .unauthorized
        case 402: return .quotaExceeded
        case 403: return .forbidden
        case 404: return .notFound
        case 422: return .validationError(message: message, details: details)
        case 429: return .rateLimited
        case 503: return .serviceUnavailable
        default: return .serverError(message: message)
        }
    }
}

extension NetworkSessionManager {
    fileprivate struct ParsedError {
        let code: String?
        let message: String
        let details: [String: Any]
    }
    
    /// 後方互換を含むパース:
    /// - 新: `{"error":{"code","message","details"}}`
    /// - 旧: `{"error":"message"}`
    nonisolated fileprivate static func parseErrorPayload(_ data: Data) -> ParsedError {
        guard
            let obj = try? JSONSerialization.jsonObject(with: data),
            let root = obj as? [String: Any]
        else {
            return ParsedError(code: nil, message: "", details: [:])
        }
        
        if let err = root["error"] as? [String: Any] {
            let code = err["code"] as? String
            let message = err["message"] as? String ?? ""
            let details = err["details"] as? [String: Any] ?? [:]
            return ParsedError(code: code, message: message, details: details)
        }
        
        if let legacy = root["error"] as? String {
            return ParsedError(code: nil, message: legacy, details: [:])
        }
        
        // さらに旧: `{"message": "...", "details": {...}}` のような形も受けておく
        let message = root["message"] as? String ?? ""
        let details = root["details"] as? [String: Any] ?? [:]
        return ParsedError(code: root["code"] as? String, message: message, details: details)
    }
}
