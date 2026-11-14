import Foundation
import OSLog

/// Consume pending state before the network await so later answers cannot be
/// erased by completion of an older request.
struct ProfileSyncBuffer {
    private var pending: UserProfile?
    var hasPending: Bool { pending != nil }

    mutating func enqueue(_ profile: UserProfile) { pending = profile }

    mutating func take() -> UserProfile? {
        defer { pending = nil }
        return pending
    }

    mutating func restoreUnlessNewer(_ profile: UserProfile) {
        if pending == nil { pending = profile }
    }
}

actor ProfileSyncService {
    static let shared = ProfileSyncService()
    
    private let logger = Logger(subsystem: "com.anicca.ios", category: "ProfileSyncService")
    private var buffer = ProfileSyncBuffer()
    private var isSyncing = false
    
    private init() {}
    
    func enqueue(profile: UserProfile, sensorAccess: [String: Bool]? = nil) async {
        // v0.4: 匿名ユーザーでもdevice_idで同期する（Apple Sign In不要）
        
        buffer.enqueue(profile)
        
        guard !isSyncing else {
            logger.debug("Sync already in progress, queued profile will be synced next")
            return
        }
        
        await performSync()
    }
    
    private func performSync() async {
        guard !isSyncing else { return }
        isSyncing = true
        defer { isSyncing = false }

        while let profile = buffer.take() {
            let authStatus = await MainActor.run { AppState.shared.authStatus }
            let deviceId = await MainActor.run { AppState.shared.resolveDeviceId() }
            let userId: String
            if case .signedIn(let credentials) = authStatus {
                userId = credentials.userId
            } else {
                userId = deviceId
            }
            do {
                try await syncProfile(deviceId: deviceId, userId: userId, profile: profile)
                logger.info("Profile synced successfully")
            } catch {
                buffer.restoreUnlessNewer(profile)
                logger.error("Profile sync failed: \(error.localizedDescription, privacy: .public)")
                return
            }
        }
    }

    private func syncProfile(
        deviceId: String,
        userId: String,
        profile: UserProfile
    ) async throws {
        let profileSyncURL = await MainActor.run { AppConfig.profileSyncURL }
        var request = URLRequest(url: profileSyncURL)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(deviceId, forHTTPHeaderField: "device-id")
        request.setValue(userId, forHTTPHeaderField: "user-id")
        
        logger.debug("Syncing profile for device: \(deviceId), user: \(userId)")
        
        let payload = await MainActor.run {
            AppState.shared.profileSyncPayload(for: profile)
        }
        
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        
        let (data, response) = try await NetworkSessionManager.shared.session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw ProfileSyncError.invalidResponse
        }
        
        guard (200..<300).contains(httpResponse.statusCode) else {
            let statusCode = httpResponse.statusCode
            if let errorData = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let message = errorData["error"] as? String {
                logger.error("Sync failed with status \(statusCode): \(message, privacy: .public)")
            }
            throw ProfileSyncError.httpError(statusCode)
        }
    }
    
    func retryPendingSyncIfNeeded() async {
        guard buffer.hasPending, !isSyncing else { return }
        await performSync()
    }
}

enum ProfileSyncError: Error {
    case invalidResponse
    case httpError(Int)
}
