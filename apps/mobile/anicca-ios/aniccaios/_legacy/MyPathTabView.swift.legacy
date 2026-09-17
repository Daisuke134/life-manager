import SwiftUI
import RevenueCat
import RevenueCatUI

/// My Path タブ - ユーザーが選択した問題（苦しみ）のリストを表示
struct MyPathTabView: View {
    @EnvironmentObject private var appState: AppState
    @State private var showAddSheet = false
    @State private var showSignOutConfirm = false
    @State private var showDeleteAccountConfirm = false
    @State private var isDeletingAccount = false
    @State private var deleteAccountError: Error?
    @State private var showingManageSubscription = false
    #if DEBUG
    @State private var showLLMCacheEmptyAlert = false
    #endif
    @State private var showUpgradePaywall = false
    @State private var problemToDelete: ProblemType?
    @State private var selectedProblem: ProblemType?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    // ヘッダー説明
                    Text(String(localized: "mypath_header_description"))
                        .font(.subheadline)
                        .foregroundStyle(AppTheme.Colors.secondaryLabel)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 20)
                        .padding(.top, 8)

                    // 今向き合っている課題セクション
                    VStack(alignment: .leading, spacing: 12) {
                        Text(String(localized: "mypath_section_current_struggles"))
                            .font(.headline)
                            .foregroundStyle(AppTheme.Colors.label)
                            .padding(.horizontal, 20)

                        if userProblems.isEmpty {
                            emptyStateView
                        } else {
                            List {
                                ForEach(userProblems, id: \.self) { problem in
                                    Button { selectedProblem = problem } label: {
                                        HStack(spacing: 12) {
                                            Text(problem.icon)
                                                .font(.system(size: 32))

                                            Text(problem.displayName)
                                                .font(.headline)
                                                .foregroundStyle(AppTheme.Colors.label)

                                            Spacer()

                                            Image(systemName: "chevron.right")
                                                .font(.system(size: 14))
                                                .foregroundStyle(AppTheme.Colors.secondaryLabel)
                                        }
                                        .padding(16)
                                        .background(AppTheme.Colors.cardBackground)
                                        .clipShape(RoundedRectangle(cornerRadius: 12))
                                    }
                                    .buttonStyle(.plain)
                                    .listRowBackground(Color.clear)
                                    .listRowSeparator(.hidden)
                                    .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
                                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                                        Button(role: .destructive) {
                                            problemToDelete = problem
                                        } label: {
                                            Label(String(localized: "problem_delete_confirm"), systemImage: "trash")
                                        }
                                    }
                                }
                            }
                            .listStyle(.plain)
                            .frame(height: CGFloat(userProblems.count) * 88)
                            .padding(.horizontal, 0)
                        }
                    }

                    // Subscription セクション
                    subscriptionSection
                        .padding(.horizontal, 16)
                        .padding(.top, 24)

                    // Account セクション（サインイン時のみ）
                    if appState.isSignedIn {
                        accountSection
                            .padding(.horizontal, 16)
                            .padding(.top, 8)
                    }

                    // DEBUG: テスト状態注入UI
                    #if DEBUG
                    debugStateInjectionSection
                        .padding(.top, 24)
                    #endif
                }
                .padding(.bottom, 0)
            }
            .navigationTitle(String(localized: "tab_mypath"))
            .accessibilityIdentifier("mypath-root")
            .background(AppBackground())
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: { showAddSheet = true }) {
                        Image(systemName: "plus")
                            .foregroundStyle(AppTheme.Colors.buttonSelected)
                    }
                }
            }
            .sheet(isPresented: $showAddSheet) {
                AddProblemSheetView()
                    .environmentObject(appState)
            }
            .sheet(item: $selectedProblem) { problem in
                DeepDiveSheetView(problem: problem)
                    .environmentObject(appState)
            }
            .alert(String(localized: "common_error"), isPresented: Binding(
                get: { deleteAccountError != nil },
                set: { if !$0 { deleteAccountError = nil } }
            )) {
                Button(String(localized: "common_ok")) { deleteAccountError = nil }
            } message: {
                if let error = deleteAccountError { Text(error.localizedDescription) }
            }
            .alert(String(localized: "problem_delete_title"), isPresented: Binding(
                get: { problemToDelete != nil },
                set: { if !$0 { problemToDelete = nil } }
            )) {
                Button(String(localized: "problem_delete_confirm"), role: .destructive) {
                    if let problem = problemToDelete {
                        appState.removeProblem(problem)
                        problemToDelete = nil
                    }
                }
                Button(String(localized: "common_cancel"), role: .cancel) {
                    problemToDelete = nil
                }
            }
        }
    }

    private var userProblems: [ProblemType] {
        appState.userProfile.struggles.compactMap { ProblemType(rawValue: $0) }
    }

    // MARK: - Subscription Section

    @ViewBuilder
    private var subscriptionSection: some View {
        if appState.subscriptionInfo.plan == .free {
            // Free: セカンダリボタン（Upgrade to Pro）
            Button {
                showUpgradePaywall = true
            } label: {
                Text(String(localized: "single_screen_subscribe"))
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(AppTheme.Colors.buttonSelected)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 12)  // 44pt タップエリア確保
                    .background(AppTheme.Colors.buttonUnselected)
                    .clipShape(Capsule())
            }
            .sheet(isPresented: $showUpgradePaywall) {
                paywallContent
            }
        } else {
            // Pro: セカンダリボタン（Manage Subscription）
            Button {
                showingManageSubscription = true
            } label: {
                Text(String(localized: "single_screen_cancel_subscription"))
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(AppTheme.Colors.buttonSelected)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 12)  // 44pt タップエリア確保
                    .background(AppTheme.Colors.buttonUnselected)
                    .clipShape(Capsule())
            }
            .sheet(isPresented: $showingManageSubscription) {
                customerCenterContent
            }
        }
    }

    @ViewBuilder
    private var paywallContent: some View {
        PaywallVariantBView(
            variant: "rc_experiment",
            onPurchaseSuccess: { _ in showUpgradePaywall = false },
            onDismiss: { showUpgradePaywall = false }
        )
    }

    // MARK: - Account Section

    @ViewBuilder
    private var accountSection: some View {
        VStack(spacing: 16) {
            // Sign Out: テキストリンク風（グレー）
            Button {
                showSignOutConfirm = true
            } label: {
                Text(String(localized: "single_screen_sign_out"))
                    .font(.subheadline)
                    .foregroundStyle(AppTheme.Colors.secondaryLabel)
                    .frame(minHeight: 44)  // 44pt タップエリア確保
            }
            .alert(String(localized: "sign_out_confirm_title"), isPresented: $showSignOutConfirm) {
                Button(String(localized: "common_cancel"), role: .cancel) { }
                Button(String(localized: "single_screen_sign_out"), role: .destructive) {
                    signOut()
                }
            } message: {
                Text(String(localized: "sign_out_confirm_message"))
            }

            // Delete Account: テキストリンク風（システム赤）
            Button {
                showDeleteAccountConfirm = true
            } label: {
                Text(String(localized: "single_screen_delete_account"))
                    .font(.subheadline)
                    .foregroundStyle(Color(.systemRed))  // ダークモード対応
                    .frame(minHeight: 44)  // 44pt タップエリア確保
            }
            .alert(String(localized: "delete_account_confirm_title"), isPresented: $showDeleteAccountConfirm) {
                Button(String(localized: "common_cancel"), role: .cancel) { }
                Button(String(localized: "single_screen_delete_account"), role: .destructive) {
                    deleteAccount()
                }
            } message: {
                Text(String(localized: "delete_account_confirm_message"))
            }
        }
    }

    // MARK: - Customer Center

    @ViewBuilder
    private var customerCenterContent: some View {
        RevenueCatUI.CustomerCenterView()
            .onCustomerCenterRestoreCompleted { customerInfo in
                Task {
                    let subscription = SubscriptionInfo(info: customerInfo)
                    await MainActor.run { appState.updateSubscriptionInfo(subscription) }
                }
            }
    }

    // MARK: - Actions

    private func signOut() {
        appState.signOutPreservingSensorAccess()
    }

    private func deleteAccount() {
        Task {
            isDeletingAccount = true
            deleteAccountError = nil
            defer { isDeletingAccount = false }

            guard case .signedIn(let credentials) = appState.authStatus else {
                await MainActor.run {
                    deleteAccountError = NSError(domain: "AccountDeletionError", code: 1, userInfo: [NSLocalizedDescriptionKey: "Not signed in"])
                }
                return
            }

            var request = URLRequest(url: AppConfig.proxyBaseURL.appendingPathComponent("mobile/account"))
            request.httpMethod = "DELETE"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue(AppState.shared.resolveDeviceId(), forHTTPHeaderField: "device-id")
            request.setValue(credentials.userId, forHTTPHeaderField: "user-id")
            try? await NetworkSessionManager.shared.setAuthHeaders(for: &request)

            do {
                let (_, response) = try await NetworkSessionManager.shared.session.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse else {
                    throw NSError(domain: "AccountDeletionError", code: 2, userInfo: [NSLocalizedDescriptionKey: "Invalid response"])
                }
                if httpResponse.statusCode == 204 {
                    await SubscriptionManager.shared.handleLogout()
                    await MainActor.run { appState.signOutAndWipe() }
                } else {
                    throw NSError(domain: "AccountDeletionError", code: httpResponse.statusCode, userInfo: [NSLocalizedDescriptionKey: "Server error: \(httpResponse.statusCode)"])
                }
            } catch {
                await MainActor.run { deleteAccountError = error }
            }
        }
    }

    // MARK: - DEBUG State Injection

    #if DEBUG
    @ViewBuilder
    private var debugStateInjectionSection: some View {
        VStack(spacing: 12) {
            Text("DEBUG: State Injection")
                .font(.caption)
                .foregroundStyle(.gray)

            Button {
                let testCredentials = UserCredentials(
                    userId: "test-user-id-\(UUID().uuidString.prefix(8))",
                    displayName: "Test User",
                    email: "test@example.com",
                    jwtAccessToken: nil
                )
                appState.setAuthStatus(.signedIn(testCredentials))
            } label: {
                Text("Set Signed In")
                    .font(.subheadline)
                    .foregroundStyle(.blue)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Color.blue.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .accessibilityIdentifier("debug_set_signed_in")

            Button {
                let proInfo = SubscriptionInfo(
                    plan: .pro,
                    status: "active",
                    currentPeriodEnd: Date().addingTimeInterval(86400 * 30),
                    managementURL: nil,
                    lastSyncedAt: .now,
                    productIdentifier: nil,
                    planDisplayName: "Pro",
                    priceDescription: nil,
                    monthlyUsageLimit: nil,
                    monthlyUsageRemaining: nil,
                    monthlyUsageCount: nil,
                    willRenew: true
                )
                appState.updateSubscriptionInfo(proInfo)
            } label: {
                Text("Set Pro Plan")
                    .font(.subheadline)
                    .foregroundStyle(.purple)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Color.purple.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .accessibilityIdentifier("debug_set_pro")

            Button {
                appState.signOutPreservingSensorAccess()
            } label: {
                Text("Reset to Free + Signed Out")
                    .font(.subheadline)
                    .foregroundStyle(.red)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Color.red.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .accessibilityIdentifier("debug_reset_state")

            Divider()
                .padding(.vertical, 8)

            Text("DEBUG: Nudge Test Buttons")
                .font(.caption)
                .foregroundStyle(.gray)

            LazyVStack(spacing: 8) {
                ForEach(ProblemType.allCases, id: \.self) { problemType in
                    Button {
                        let content = NudgeContent.contentForToday(for: problemType)
                        appState.pendingNudgeCard = content
                    } label: {
                        HStack {
                            Text(problemType.icon)
                            Text(problemType.displayName)
                                .font(.subheadline)
                                .foregroundStyle(.blue)
                            Spacer()
                        }
                        .padding(.vertical, 8)
                        .padding(.horizontal, 12)
                        .background(Color.blue.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                    .accessibilityIdentifier("debug-nudge-test-\(problemType.rawValue)")
                }
            }

            Divider()
                .padding(.vertical, 8)

            Text("DEBUG: LLM Nudge Test")
                .font(.caption)
                .foregroundStyle(.gray)

            Button {
                if let realNudge = LLMNudgeCache.shared.getFirstNudge() {
                    let content = NudgeContent.content(from: realNudge)
                    appState.pendingNudgeCard = content
                } else {
                    showLLMCacheEmptyAlert = true
                }
            } label: {
                HStack {
                    Text("🤖")
                    Text("Show LLM Nudge (real data)")
                        .font(.subheadline)
                        .foregroundStyle(.green)
                    Spacer()
                    Text("\(LLMNudgeCache.shared.count)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Circle()
                        .fill(Color.blue.opacity(0.6))
                        .frame(width: 6, height: 6)
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 12)
                .background(Color.green.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .accessibilityIdentifier("debug-nudge-test-llm")
            .alert("LLM Cache Empty", isPresented: $showLLMCacheEmptyAlert) {
                Button("OK", role: .cancel) {}
            } message: {
                Text("LLM Nudge がまだ取得されていません。アプリ起動時に自動フェッチされます。")
            }

            NavigationLink {
                LLMNudgeDebugView()
            } label: {
                HStack {
                    Text("📋")
                    Text("Nudge Cache List")
                        .font(.subheadline)
                        .foregroundStyle(.orange)
                    Spacer()
                    Text("\(LLMNudgeCache.shared.count) cached")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 12)
                .background(Color.orange.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .accessibilityIdentifier("debug-nudge-cache-list")

            Divider()
                .padding(.vertical, 8)

            Text("DEBUG: E2E")
                .font(.caption)
                .foregroundStyle(.gray)

            NavigationLink {
                E2ENotificationDebugView()
            } label: {
                HStack {
                    Text("🧪")
                    Text("E2E Notification Debug")
                        .font(.subheadline)
                        .foregroundStyle(.blue)
                    Spacer()
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 12)
                .background(Color.blue.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .accessibilityIdentifier("debug-e2e-notification")
        }
        .padding(.horizontal, 16)
    }
    #endif

    private var emptyStateView: some View {
        VStack(spacing: 16) {
            Image(systemName: "leaf.fill")
                .font(.system(size: 48))
                .foregroundStyle(AppTheme.Colors.secondaryLabel)

            Text(String(localized: "mypath_empty_title"))
                .font(.headline)
                .foregroundStyle(AppTheme.Colors.label)

            PrimaryButton(
                title: String(localized: "mypath_empty_action"),
                style: .primary
            ) {
                showAddSheet = true
            }
            .padding(.horizontal, 40)
        }
        .padding(40)
    }
}



// MARK: - ProblemType Identifiable
extension ProblemType: Identifiable {
    var id: String { rawValue }
}

#Preview {
    MyPathTabView()
        .environmentObject(AppState.shared)
}
