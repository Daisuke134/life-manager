// App/ScreenshotDebugManager.swift
// l.md Bible Step 1: CommandLine引数でモックデータ注入と画面遷移を制御
// Pattern: l.md DebugManager.configure() — called from onAppear in aniccaiosApp

#if DEBUG
import Foundation

final class ScreenshotDebugManager {
    static let shared = ScreenshotDebugManager()
    private init() {}

    func configure() {
        AppState.shared.configureForScreenshots()
    }
}
#endif
