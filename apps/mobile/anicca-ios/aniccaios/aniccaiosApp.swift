//
//  aniccaiosApp.swift
//  aniccaios
//
//  Created by CBNS03 on 2025/11/02.
//

import Combine
import SwiftUI

@main
struct aniccaiosApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var appState = AppState.shared

    var body: some Scene {
        WindowGroup {
            ContentRouterView()
                .environmentObject(appState)
                // v3: OSロケールに追従（locale overrideを撤廃）
                .tint(AppTheme.Colors.accent)
                .onAppear {
                    #if DEBUG
                    ScreenshotDebugManager.shared.configure()
                    #endif
                }
                .onOpenURL { url in
                    guard url.scheme == "anicca" else { return }

                    // 4-daily affirmation deep link: anicca://quote/<qid>
                    if url.host == "quote" {
                        let qid = url.lastPathComponent
                        if !qid.isEmpty && qid != "quote" {
                            NotificationCenter.default.post(
                                name: .aniccaScrollToQuote,
                                object: nil,
                                userInfo: ["quoteId": qid]
                            )
                        }
                        return
                    }
                }
        }
    }
}
