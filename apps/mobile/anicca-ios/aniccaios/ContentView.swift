//
//  ContentView.swift
//  aniccaios
//
//  Created by CBNS03 on 2025/11/02.
//

import SwiftUI

struct ContentRouterView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        // プロファイル取得中のProgressは、オンボーディング完了後のみ（オンボーディング中の遷移を邪魔しない）
        if appState.isBootstrappingProfile && appState.isOnboardingComplete {
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(AppBackground())
        } else if !appState.isOnboardingComplete {
            OnboardingFlowView()
        } else {
            switch appState.authStatus {
            case .signedOut:
                // v3-ui.md: Sign in は Skip 可能。オンボーディング完了後はアプリに進める。
                FeedRootView()
            case .signingIn:
                AuthenticationProcessingView()
            case .signedIn:
                FeedRootView()
            }
        }
    }
}

struct AuthenticationProcessingView: View {
    var body: some View {
        VStack(spacing: 24) {
            ProgressView()
                .scaleEffect(1.5)
            Text("common_signing_in")
                .font(.headline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppBackground())
    }
}

#Preview {
    ContentRouterView()
        .environmentObject(AppState.shared)
}
