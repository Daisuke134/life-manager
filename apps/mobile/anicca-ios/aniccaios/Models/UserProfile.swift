import Foundation

enum LanguagePreference: String, Codable {
    case ja
    case en
    case de
    case fr
    case es
    case ptBR = "pt-BR"
    
    /// プロンプト内のLANGUAGE LOCK用（ハードコーディングで確実に正しい言語名を返す）
    var languageLine: String {
        switch self {
        case .ja:
            return "日本語"
        case .en:
            return "English"
        case .de:
            return "Deutsch"
        case .fr:
            return "Français"
        case .es:
            return "Español"
        case .ptBR:
            return "Português (Brasil)"
        }
    }
    
    /// UI表示用のローカライズされた言語名
    var displayName: String {
        switch self {
        case .ja:
            return NSLocalizedString("language_preference_ja", comment: "")
        case .en:
            return NSLocalizedString("language_preference_en", comment: "")
        case .de:
            return NSLocalizedString("language_preference_de", comment: "")
        case .fr:
            return NSLocalizedString("language_preference_fr", comment: "")
        case .es:
            return NSLocalizedString("language_preference_es", comment: "")
        case .ptBR:
            return NSLocalizedString("language_preference_ptBR", comment: "")
        }
    }
    
    static func detectDefault(locale: Locale = .current) -> Self {
        let preferred = (Locale.preferredLanguages.first ?? locale.identifier).lowercased()
        if preferred.hasPrefix("ja") { return .ja }
        if preferred.hasPrefix("de") { return .de }
        if preferred.hasPrefix("fr") { return .fr }
        if preferred.hasPrefix("es") { return .es }
        if preferred.hasPrefix("pt-br") || preferred.hasPrefix("pt_br") || preferred.hasPrefix("pt") { return .ptBR }
        return .en
    }
}

// MARK: - v0.3 Traits models
enum NudgeIntensity: String, Codable, CaseIterable {
    case quiet
    case normal
    case active
    
    static var `default`: Self { .normal }
}

struct Big5Scores: Codable, Equatable {
    var openness: Int
    var conscientiousness: Int
    var extraversion: Int
    var agreeableness: Int
    var neuroticism: Int
    var summary: String?
}

struct UserProfile: Codable {
    var displayName: String
    
    // Demographics (onboarding)
    var acquisitionSource: String?
    var gender: String?
    var ageRange: String?
    
    var preferredLanguage: LanguagePreference
    var sleepLocation: String
    var trainingFocus: [String]
    
    // 追加フィールド（既存）
    var wakeLocation: String
    var wakeRoutines: [String]
    var sleepRoutines: [String]
    var trainingGoal: String
    
    // v0.3: traits / personalization
    var ideals: [String]
    var struggles: [String]
    var big5: Big5Scores?
    var keywords: [String]
    var summary: String
    var nudgeIntensity: NudgeIntensity
    var stickyMode: Bool

    // Onboarding v2: goals and struggle frequency
    var goals: [String]
    var struggleFrequency: String?

    // Phase 3: Proactive Agent
    var problemDetails: [String: [String]]  // 深掘り回答（問題ID: 選択した選択肢）
    var customProblems: [CustomProblem]      // カスタム課題
    
    // Backward-compatible aliases（既存UI/ロジックを壊さない）
    var idealTraits: [String] {
        get { ideals }
        set { ideals = newValue }
    }
    
    var problems: [String] {
        get { struggles }
        set { struggles = newValue }
    }
    
    var stickyModeEnabled: Bool {
        get { stickyMode }
        set { stickyMode = newValue }
    }
    
    init(
        displayName: String = "",
        acquisitionSource: String? = nil,
        gender: String? = nil,
        ageRange: String? = nil,
        preferredLanguage: LanguagePreference = LanguagePreference.detectDefault(),
        sleepLocation: String = "",
        trainingFocus: [String] = [],
        wakeLocation: String = "",
        wakeRoutines: [String] = [],
        sleepRoutines: [String] = [],
        trainingGoal: String = "",
        ideals: [String] = [],
        struggles: [String] = [],
        big5: Big5Scores? = nil,
        keywords: [String] = [],
        summary: String = "",
        nudgeIntensity: NudgeIntensity = .default,
        stickyMode: Bool = true,
        goals: [String] = [],
        struggleFrequency: String? = nil,
        problemDetails: [String: [String]] = [:],
        customProblems: [CustomProblem] = []
    ) {
        self.displayName = displayName
        self.acquisitionSource = acquisitionSource
        self.gender = gender
        self.ageRange = ageRange
        self.preferredLanguage = preferredLanguage
        self.sleepLocation = sleepLocation
        self.trainingFocus = trainingFocus
        self.wakeLocation = wakeLocation
        self.wakeRoutines = wakeRoutines
        self.sleepRoutines = sleepRoutines
        self.trainingGoal = trainingGoal
        self.ideals = ideals
        self.struggles = struggles
        self.big5 = big5
        self.keywords = keywords
        self.summary = summary
        self.nudgeIntensity = nudgeIntensity
        self.stickyMode = stickyMode
        self.goals = goals
        self.struggleFrequency = struggleFrequency
        self.problemDetails = problemDetails
        self.customProblems = customProblems
    }
    
    // 既存データとの互換性のためのカスタムデコーディング
    enum CodingKeys: String, CodingKey {
        case displayName, preferredLanguage, sleepLocation, trainingFocus
        
        // Demographics (onboarding)
        case acquisitionSource, gender, ageRange
        
        case wakeLocation, wakeRoutines, sleepRoutines, trainingGoal
        
        // v0.3
        case ideals, struggles, big5, keywords, summary, nudgeIntensity, stickyMode
        
        // Onboarding v2
        case goals, struggleFrequency

        // Phase 3: Proactive Agent
        case problemDetails, customProblems

        // legacy (read-only)
        case idealTraits
        case problems
        case stickyModeEnabled
        case wakeStickyModeEnabled
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName) ?? ""
        
        // Demographics (onboarding)
        acquisitionSource = try container.decodeIfPresent(String.self, forKey: .acquisitionSource)
        gender = try container.decodeIfPresent(String.self, forKey: .gender)
        ageRange = try container.decodeIfPresent(String.self, forKey: .ageRange)
        
        preferredLanguage = try container.decodeIfPresent(LanguagePreference.self, forKey: .preferredLanguage) ?? LanguagePreference.detectDefault()
        sleepLocation = try container.decodeIfPresent(String.self, forKey: .sleepLocation) ?? ""
        trainingFocus = try container.decodeIfPresent([String].self, forKey: .trainingFocus) ?? []
        wakeLocation = try container.decodeIfPresent(String.self, forKey: .wakeLocation) ?? ""
        wakeRoutines = try container.decodeIfPresent([String].self, forKey: .wakeRoutines) ?? []
        sleepRoutines = try container.decodeIfPresent([String].self, forKey: .sleepRoutines) ?? []
        trainingGoal = try container.decodeIfPresent(String.self, forKey: .trainingGoal) ?? ""
        
        // v0.3 traits (fallback to legacy)
        if let decodedIdeals = try container.decodeIfPresent([String].self, forKey: .ideals) {
            ideals = decodedIdeals
        } else {
            ideals = try container.decodeIfPresent([String].self, forKey: .idealTraits) ?? []
        }
        if let decodedStruggles = try container.decodeIfPresent([String].self, forKey: .struggles) {
            struggles = decodedStruggles
        } else {
            struggles = try container.decodeIfPresent([String].self, forKey: .problems) ?? []
        }
        big5 = try container.decodeIfPresent(Big5Scores.self, forKey: .big5)
        keywords = try container.decodeIfPresent([String].self, forKey: .keywords) ?? []
        summary = try container.decodeIfPresent(String.self, forKey: .summary) ?? ""
        nudgeIntensity = try container.decodeIfPresent(NudgeIntensity.self, forKey: .nudgeIntensity) ?? .default
        
        // Sticky (fallback to legacy keys)
        if let sticky = try container.decodeIfPresent(Bool.self, forKey: .stickyMode) {
            stickyMode = sticky
        } else if let sticky = try container.decodeIfPresent(Bool.self, forKey: .stickyModeEnabled) {
            stickyMode = sticky
        } else if let oldSticky = try container.decodeIfPresent(Bool.self, forKey: .wakeStickyModeEnabled) {
            stickyMode = oldSticky
        } else {
            stickyMode = true
        }

        // Onboarding v2
        goals = try container.decodeIfPresent([String].self, forKey: .goals) ?? []
        struggleFrequency = try container.decodeIfPresent(String.self, forKey: .struggleFrequency)

        // Phase 3: Proactive Agent
        problemDetails = try container.decodeIfPresent([String: [String]].self, forKey: .problemDetails) ?? [:]
        customProblems = try container.decodeIfPresent([CustomProblem].self, forKey: .customProblems) ?? []
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(displayName, forKey: .displayName)
        
        // Demographics (onboarding)
        try container.encodeIfPresent(acquisitionSource, forKey: .acquisitionSource)
        try container.encodeIfPresent(gender, forKey: .gender)
        try container.encodeIfPresent(ageRange, forKey: .ageRange)
        
        try container.encode(preferredLanguage, forKey: .preferredLanguage)
        try container.encode(sleepLocation, forKey: .sleepLocation)
        try container.encode(trainingFocus, forKey: .trainingFocus)
        try container.encode(wakeLocation, forKey: .wakeLocation)
        try container.encode(wakeRoutines, forKey: .wakeRoutines)
        try container.encode(sleepRoutines, forKey: .sleepRoutines)
        try container.encode(trainingGoal, forKey: .trainingGoal)
        
        // v0.3 keys only
        try container.encode(ideals, forKey: .ideals)
        try container.encode(struggles, forKey: .struggles)
        try container.encodeIfPresent(big5, forKey: .big5)
        try container.encode(keywords, forKey: .keywords)
        try container.encode(summary, forKey: .summary)
        try container.encode(nudgeIntensity, forKey: .nudgeIntensity)
        try container.encode(stickyMode, forKey: .stickyMode)

        // Onboarding v2
        try container.encode(goals, forKey: .goals)
        try container.encodeIfPresent(struggleFrequency, forKey: .struggleFrequency)

        // Phase 3: Proactive Agent
        try container.encode(problemDetails, forKey: .problemDetails)
        try container.encode(customProblems, forKey: .customProblems)
        // legacy keysはデコード互換専用なのでエンコードしない
    }
}

struct UserCredentials: Codable {
    let userId: String
    let displayName: String
    let email: String?
    // JWT Access Token (optional for backward compatibility)
    var jwtAccessToken: String?
    var accessTokenExpiresAt: Date?
}

enum AuthStatus: Codable, Equatable {
    case signedOut
    case signingIn
    case signedIn(UserCredentials)
    
    static func == (lhs: AuthStatus, rhs: AuthStatus) -> Bool {
        switch (lhs, rhs) {
        case (.signedOut, .signedOut), (.signingIn, .signingIn):
            return true
        case (.signedIn(let lhsCreds), .signedIn(let rhsCreds)):
            return lhsCreds.userId == rhsCreds.userId
        default:
            return false
        }
    }
}
