import Foundation
import OSLog

actor ProfileSyncService {
    static let shared = ProfileSyncService()
    
    private let logger = Logger(subsystem: "com.anicca.ios", category: "ProfileSyncService")
    private var pendingSync: UserProfile?
    private var isSyncing = false
    
    private init() {}
    
    func enqueue(profile: UserProfile, sensorAccess: [String: Bool]? = nil) async {
        // v0.4: 匿名ユーザーでもdevice_idで同期する（Apple Sign In不要）
        
        pendingSync = profile
        
        guard !isSyncing else {
            logger.debug("Sync already in progress, queued profile will be synced next")
            return
        }
        
        await performSync()
    }
    
    private func performSync() async {
        guard let profile = pendingSync else {
            isSyncing = false
            return
        }
        
        isSyncing = true
        
        // v0.4: user_idがあれば使う、なければdevice_idをuser_idとして使う
        let authStatus = await MainActor.run { AppState.shared.authStatus }
        let deviceId = await MainActor.run { AppState.shared.resolveDeviceId() }
        
        let userId: String
        if case .signedIn(let credentials) = authStatus {
            userId = credentials.userId
        } else {
            userId = deviceId
        }
        
        do {
            try await syncProfile(
                deviceId: deviceId,
                userId: userId,
                profile: profile
            )
            
            pendingSync = nil
            isSyncing = false
            
            logger.info("Profile synced successfully")
        } catch {
            logger.error("Profile sync failed: \(error.localizedDescription, privacy: .public)")
            isSyncing = false
            // Keep pendingSync for retry
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
        guard pendingSync != nil, !isSyncing else { return }
        await performSync()
    }
}

enum ProfileSyncError: Error {
    case invalidResponse
    case httpError(Int)
}
