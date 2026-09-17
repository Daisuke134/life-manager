import Foundation

actor AuthHealthCheck {
    static let shared = AuthHealthCheck()

    private var lastPing: Date?
    private let cooldown: TimeInterval = 60

    func warmBackend() async {
        if let lastPing, Date().timeIntervalSince(lastPing) < cooldown { return }
        lastPing = Date()
        let baseURL = await MainActor.run { AppConfig.appleAuthURL }
        var request = URLRequest(url: baseURL.appending(path: "health"))
        request.httpMethod = "GET"
        request.timeoutInterval = 3
        let session = URLSession(configuration: .ephemeral)
        _ = try? await session.data(for: request)
    }
}

