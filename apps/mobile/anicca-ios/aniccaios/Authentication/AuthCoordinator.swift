import AuthenticationServices
import CryptoKit
import Foundation
import OSLog

@MainActor
final class AuthCoordinator {
    static let shared = AuthCoordinator()
    
    private let logger = Logger(subsystem: "com.anicca.ios", category: "AuthCoordinator")
    private var currentNonce: String?
    // v0.4: 復元フロー用のcompletionハンドラ
    private var signInCompletion: ((Bool) -> Void)?
    
    private init() {}
    
    lazy var presentationDelegate: AuthPresentationDelegate = {
        AuthPresentationDelegate(coordinator: self)
    }()
    
    func configure(_ request: ASAuthorizationAppleIDRequest) {
        AppState.shared.setAuthStatus(.signingIn)
        
        let nonce = randomNonceString()
        currentNonce = nonce
        guard let hashedNonce = sha256Base64(nonce) else {
            logger.error("Failed to compute nonce hash")
            AppState.shared.setAuthStatus(.signedOut)
            return
        }
        
        request.requestedScopes = [.fullName, .email]
        request.nonce = hashedNonce
    }
    
    func startSignIn() {
        let nonce = randomNonceString()
        currentNonce = nonce
        guard let hashedNonce = sha256Base64(nonce) else {
            logger.error("Failed to compute nonce hash")
            return
        }
        
        let appleIDProvider = ASAuthorizationAppleIDProvider()
        let request = appleIDProvider.createRequest()
        request.requestedScopes = [.fullName, .email]
        request.nonce = hashedNonce
        
        let authorizationController = ASAuthorizationController(authorizationRequests: [request])
        authorizationController.delegate = presentationDelegate
        authorizationController.presentationContextProvider = presentationDelegate
        
        AppState.shared.setAuthStatus(.signingIn)
        authorizationController.performRequests()
    }
    
    func completeSignIn(result: Result<ASAuthorization, Error>) {
        completeSignIn(result: result, completion: nil)
    }
    
    // v0.4: completionハンドラ付きバージョン（復元フロー用）
    func completeSignIn(result: Result<ASAuthorization, Error>, completion: ((Bool) -> Void)?) {
        signInCompletion = completion
        
        switch result {
        case .success(let authorization):
            handleAuthorization(authorization)
        case .failure(let error):
            // 既にサインイン済みなら無視（AuthorizationError 1000 などの後着エラー対策）
            if case .signedIn = AppState.shared.authStatus {
                signInCompletion?(true)
                return
            }
            logger.error("Apple sign in failed: \(error.localizedDescription, privacy: .public)")
            AppState.shared.setAuthStatus(.signedOut)
            signInCompletion?(false)
        }
    }
    
    func signOut() {
        AppState.shared.clearUserCredentials()
        AppState.shared.resetState()
    }
    
    private func handleAuthorization(_ authorization: ASAuthorization) {
        guard let appleIDCredential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            logger.error("Invalid credential type")
            AppState.shared.setAuthStatus(.signedOut)
            return
        }
        
        guard let nonce = currentNonce,
              sha256Base64(nonce) != nil,
              let identityTokenData = appleIDCredential.identityToken,
              let identityTokenString = String(data: identityTokenData, encoding: .utf8) else {
            logger.error("Missing identity token or nonce")
            AppState.shared.setAuthStatus(.signedOut)
            return
        }
        
        // Extract user info
        let userId = appleIDCredential.user
        let fullName = appleIDCredential.fullName
        let email = appleIDCredential.email
        
        let displayName = [fullName?.givenName, fullName?.familyName]
            .compactMap { $0 }
            .joined(separator: " ")
        
        // Send to backend for verification
        Task {
            await verifyWithBackend(
                identityToken: identityTokenString,
                nonce: nonce,
                userId: userId,
                displayName: displayName,  // "User"を設定しない
                email: email
            )
        }
    }
    
    private func verifyWithBackend(
        identityToken: String,
        nonce: String,
        userId: String,
        displayName: String,
        email: String?
    ) async {
        let url = AppConfig.appleAuthURL
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload: [String: Any] = [
            "identity_token": identityToken,
            "nonce": nonce,
            "user_id": userId
        ]
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)
            
            let (data, response) = try await warmSession.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse,
                  (200..<300).contains(httpResponse.statusCode) else {
                logger.error("Auth backend returned error status")
                await MainActor.run {
                    AppState.shared.setAuthStatus(.signedOut)
                }
                return
            }
            
            // Parse backend response (expected: { userId, displayName, email })
            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
               let backendUserId = json["userId"] as? String {
                
                let jwtToken = json["token"] as? String
                var expiresAt: Date? = nil
                if let expMs = json["expiresAt"] as? TimeInterval {
                    expiresAt = Date(timeIntervalSince1970: expMs / 1000)
                }
                if let rt = json["refreshToken"] as? String {
                    try? KeychainService.save(Data(rt.utf8), account: "rt")
                }
                
                var credentials = UserCredentials(
                    userId: backendUserId,
                    displayName: displayName,
                    email: email
                )
                credentials.jwtAccessToken = jwtToken
                credentials.accessTokenExpiresAt = expiresAt
                
                await MainActor.run {
                    AppState.shared.updateUserCredentials(credentials)
                }
                await AppState.shared.bootstrapProfileFromServerIfAvailable()
                
                logger.info("Sign in successful for user: \(backendUserId, privacy: .public)")
                signInCompletion?(true)
            } else {
                logger.error("Invalid backend response format")
                await MainActor.run {
                    AppState.shared.setAuthStatus(.signedOut)
                }
                signInCompletion?(false)
            }
        } catch {
            logger.error("Failed to verify with backend: \(error.localizedDescription, privacy: .public)")
            await MainActor.run {
                AppState.shared.setAuthStatus(.signedOut)
            }
            signInCompletion?(false)
        }
    }
    
    // MARK: - Nonce generation
    
    private func randomNonceString(length: Int = 32) -> String {
        precondition(length > 0)
        let charset: [Character] = Array("0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._")
        var result = ""
        var remainingLength = length
        
        while remainingLength > 0 {
            let randoms: [UInt8] = (0..<16).map { _ in
                var random: UInt8 = 0
                let errorCode = SecRandomCopyBytes(kSecRandomDefault, 1, &random)
                if errorCode != errSecSuccess {
                    fatalError("Unable to generate nonce. SecRandomCopyBytes failed with OSStatus \(errorCode)")
                }
                return random
            }
            
            randoms.forEach { random in
                if remainingLength == 0 {
                    return
                }
                
                if random < charset.count {
                    result.append(charset[Int(random)])
                    remainingLength -= 1
                }
            }
        }
        
        return result
    }
    
    private func sha256Base64(_ input: String) -> String? {
        let inputData = Data(input.utf8)
        let hashedData = SHA256.hash(data: inputData)
        return Data(hashedData).base64EncodedString()
    }
    
    private var warmSession: URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.waitsForConnectivity = false
        configuration.timeoutIntervalForRequest = 10
        return URLSession(configuration: configuration)
    }
    
}
