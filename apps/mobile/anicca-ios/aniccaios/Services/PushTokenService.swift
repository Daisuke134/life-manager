import Foundation
import UIKit
import UserNotifications
import OSLog

/// APNs device token registration (v1.6.3).
/// Stores a local "registered" flag to safely disable local Problem notifications (avoid duplicates).
@MainActor
final class PushTokenService {
    static let shared = PushTokenService()

    private let logger = Logger(subsystem: "com.anicca.ios", category: "PushTokenService")
    private let defaults = UserDefaults.standard
    private let registeredKey = "com.anicca.apnsTokenRegistered"

    private init() {}

    var isRegistered: Bool {
        defaults.bool(forKey: registeredKey)
    }

    func markUnregistered() {
        defaults.set(false, forKey: registeredKey)
    }

    func register(deviceToken: Data) async {
        let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
        guard hex.count == 64 else {
            logger.error("Invalid device token length: \(hex.count, privacy: .public)")
            return
        }

        var request = URLRequest(url: AppConfig.pushTokenRegisterURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // Bind to device (no user-id required; backend will resolve securely).
        request.setValue(AppState.shared.resolveDeviceId(), forHTTPHeaderField: "device-id")

        // Help backend pick correct timezone/lang SSOT.
        request.setValue(TimeZone.current.identifier, forHTTPHeaderField: "x-timezone")
        request.setValue(AppState.shared.effectiveLanguage.rawValue, forHTTPHeaderField: "x-lang")

        let body: [String: Any] = [
            "token": hex,
            "platform": "ios"
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, response) = try await NetworkSessionManager.shared.session.data(for: request)
            guard let http = response as? HTTPURLResponse else { return }
            if (200..<300).contains(http.statusCode) {
                // Backend must confirm remote delivery is enabled. Otherwise disabling local
                // scheduling can cause a notification blackout.
                let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
                // Only disable local Problem notifications when the server confirms
                // the user is actually eligible for remote Problem nudges (entitlement-gated).
                // This avoids a "free user blackout" if APNs config is OK but server won't send.
                let isRemoteEnabled = (json?["remoteProblemNudgesEnabled"] as? Bool) == true
                if isRemoteEnabled {
                    defaults.set(true, forKey: registeredKey)
                    // Remove any locally scheduled problem notifications to avoid duplicates once
                    // server-side APNs delivery is active.
                    await ProblemNotificationScheduler.shared.cancelAllNotifications()
                    // Also clear any free-plan scheduled ids (defensive; avoids double-delivery if plan changes).
                    let freeIds = (0..<3).map { "free_nudge_\($0)" }
                    UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: freeIds)
                } else {
                    // If remote delivery is not enabled, ensure local scheduling is NOT disabled.
                    markUnregistered()
                    logger.warning("Remote delivery not enabled; keeping local Problem notifications active")
                    // Best-effort: re-schedule local Problem notifications if we already have struggles.
                    let problems = AppState.shared.userProfile.struggles
                    if !problems.isEmpty {
                        await ProblemNotificationScheduler.shared.scheduleNotifications(for: problems)
                    }
                }
                return
            }
            // Fail-safe: if registration fails, do not keep remote-only mode enabled.
            await restoreLocalProblemNotifications()
            logger.error("Push token register failed http=\(http.statusCode, privacy: .public)")
        } catch {
            // Fail-safe: network errors should not keep remote-only mode enabled.
            await restoreLocalProblemNotifications()
            logger.error("Push token register failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func restoreLocalProblemNotifications() async {
        markUnregistered()
        let problems = AppState.shared.userProfile.struggles
        if !problems.isEmpty {
            await ProblemNotificationScheduler.shared.scheduleNotifications(for: problems)
        }
    }
}
