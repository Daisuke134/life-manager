import UserNotifications
import os.log

class NotificationService: UNNotificationServiceExtension {
    
    private let logger = Logger(subsystem: "com.anicca.ios.notification-service", category: "PreReminder")
    
    var contentHandler: ((UNNotificationContent) -> Void)?
    var bestAttemptContent: UNMutableNotificationContent?
    
    // Keychain/UserDefaults からの認証情報取得（App Groupsを使用）
    private var appGroupDefaults: UserDefaults? {
        UserDefaults(suiteName: "group.ai.anicca.app.ios")
    }
    
    private var proxyBaseURL: String {
        // Info.plist から読み込み、または App Groups UserDefaults から取得
        if let url = Bundle.main.object(forInfoDictionaryKey: "ANICCA_PROXY_BASE_URL") as? String {
            return url
        }
        return appGroupDefaults?.string(forKey: "ANICCA_PROXY_BASE_URL") ?? ""
    }
    
    override func didReceive(_ request: UNNotificationRequest,
                             withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void) {
        self.contentHandler = contentHandler
        bestAttemptContent = (request.content.mutableCopy() as? UNMutableNotificationContent)
        
        guard let bestAttemptContent = bestAttemptContent else {
            contentHandler(request.content)
            return
        }
        
        // PRE_REMINDER カテゴリの通知のみ処理
        guard request.content.categoryIdentifier == "PRE_REMINDER" else {
            contentHandler(bestAttemptContent)
            return
        }
        
        let userInfo = request.content.userInfo
        guard let habitType = userInfo["habitType"] as? String,
              let scheduledTime = userInfo["scheduledTime"] as? String else {
            logger.warning("Missing habitType or scheduledTime in userInfo")
            contentHandler(bestAttemptContent)
            return
        }
        
        let habitName = userInfo["habitName"] as? String
        
        // App Groups から認証情報を取得
        guard let userId = appGroupDefaults?.string(forKey: "userId"),
              let deviceId = appGroupDefaults?.string(forKey: "deviceId") else {
            logger.warning("Missing userId or deviceId in App Groups")
            contentHandler(bestAttemptContent)
            return
        }
        
        Task {
            await fetchAndUpdateMessage(
                bestAttemptContent: bestAttemptContent,
                habitType: habitType,
                habitName: habitName,
                scheduledTime: scheduledTime,
                userId: userId,
                deviceId: deviceId,
                contentHandler: contentHandler
            )
        }
    }
    
    private func fetchAndUpdateMessage(
        bestAttemptContent: UNMutableNotificationContent,
        habitType: String,
        habitName: String?,
        scheduledTime: String,
        userId: String,
        deviceId: String,
        contentHandler: @escaping (UNNotificationContent) -> Void
    ) async {
        guard !proxyBaseURL.isEmpty else {
            logger.error("proxyBaseURL is empty")
            contentHandler(bestAttemptContent)
            return
        }
        
        let urlString = "\(proxyBaseURL)/mobile/nudge/pre-reminder"
        guard let url = URL(string: urlString) else {
            logger.error("Invalid URL: \(urlString)")
            contentHandler(bestAttemptContent)
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(deviceId, forHTTPHeaderField: "device-id")
        request.setValue(userId, forHTTPHeaderField: "user-id")
        request.timeoutInterval = 25  // Service Extension は最大30秒
        
        var body: [String: Any] = [
            "habitType": habitType,
            "scheduledTime": scheduledTime
        ]
        if let habitName = habitName {
            body["habitName"] = habitName
        }
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            
            let (data, response) = try await URLSession.shared.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse,
                  (200..<300).contains(httpResponse.statusCode) else {
                logger.error("Non-2xx response from pre-reminder endpoint")
                contentHandler(bestAttemptContent)
                return
            }
            
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let message = json["message"] as? String, !message.isEmpty else {
                logger.warning("Empty or invalid message in response")
                contentHandler(bestAttemptContent)
                return
            }
            
            // パーソナライズされたメッセージで通知本文を更新
            bestAttemptContent.body = message
            
            // nudgeIdをuserInfoに追加（フィードバック用）
            if let nudgeId = json["nudgeId"] as? String {
                var updatedUserInfo = bestAttemptContent.userInfo
                updatedUserInfo["nudgeId"] = nudgeId
                bestAttemptContent.userInfo = updatedUserInfo
            }
            
            logger.info("Updated notification with personalized message: \(message.prefix(30))...")
            contentHandler(bestAttemptContent)
            
        } catch {
            logger.error("Failed to fetch pre-reminder message: \(error.localizedDescription)")
            contentHandler(bestAttemptContent)
        }
    }
    
    override func serviceExtensionTimeWillExpire() {
        // 時間切れの場合はデフォルトメッセージで表示
        if let contentHandler = contentHandler, let bestAttemptContent = bestAttemptContent {
            contentHandler(bestAttemptContent)
        }
    }
}
