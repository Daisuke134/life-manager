import Foundation

nonisolated struct ToolkitObjectResponse: Codable, Sendable {
    let object: AIResponseData
}

nonisolated struct AIResponseData: Codable, Sendable {
    let honne: String
    let psychologicalState: String
    let suggestedResponse: String
    let emotionLevel: Int
}

@Observable
@MainActor
class AIService {
    var isAnalyzing = false
    var errorMessage: String?

    private let toolkitURL: String = Config.EXPO_PUBLIC_TOOLKIT_URL

    func analyzeMessage(_ text: String, relationship: RelationshipType) async -> TranslationResult? {
        isAnalyzing = true
        errorMessage = nil
        defer { isAnalyzing = false }

        do {
            guard !toolkitURL.isEmpty else {
                errorMessage = "AIサービスのURLが設定されていません。"
                return nil
            }

            guard let url = URL(string: "\(toolkitURL)/llm/object") else {
                errorMessage = "AIサービスに接続できません。"
                return nil
            }

            let prompt = """
            あなたは人間関係の専門家であり、心理カウンセラーです。
            ユーザーが送ってきたメッセージや会話文を分析し、JSON形式で回答してください。

            関係性: \(relationship.displayName)

            以下のメッセージを分析してください：

            \(text)
            """

            let schema: [String: Any] = [
                "type": "object",
                "properties": [
                    "honne": ["type": "string"],
                    "psychologicalState": ["type": "string"],
                    "suggestedResponse": ["type": "string"],
                    "emotionLevel": ["type": "number", "minimum": 1, "maximum": 5]
                ],
                "required": ["honne", "psychologicalState", "suggestedResponse", "emotionLevel"]
            ]

            let requestBody: [String: Any] = [
                "messages": [
                    ["role": "user", "content": prompt]
                ],
                "schema": schema
            ]

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.timeoutInterval = 60
            request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)

            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                errorMessage = "サーバーからの応答が無効です。"
                return nil
            }

            guard (200...299).contains(httpResponse.statusCode) else {
                let responseText = String(data: data, encoding: .utf8) ?? ""
                print("[AIService] HTTP \(httpResponse.statusCode): \(responseText)")
                errorMessage = "AI分析中にエラーが発生しました（\(httpResponse.statusCode)）。もう一度お試しください。"
                return nil
            }

            let toolkitResponse = try JSONDecoder().decode(ToolkitObjectResponse.self, from: data)
            let aiData = toolkitResponse.object

            return TranslationResult(
                originalText: text,
                relationship: relationship,
                honne: aiData.honne,
                psychologicalState: aiData.psychologicalState,
                suggestedResponse: aiData.suggestedResponse,
                emotionLevel: min(5, max(1, aiData.emotionLevel))
            )
        } catch {
            print("[AIService] Error: \(error)")
            errorMessage = "分析中にエラーが発生しました。もう一度お試しください。"
            return nil
        }
    }
}
