import SwiftUI
import UIKit
import UserNotifications
import OSLog
import Combine
import RevenueCat
import RevenueCatUI

/// Home settings share the onboarding palette and typography.
struct SettingsSheet: View {
    @EnvironmentObject var themeStore: ThemeStore
    @EnvironmentObject var likedStore: LikedQuotesStore
    @Environment(\.dismiss) private var dismiss

    @State private var showSignOutConfirmation = false
    @State private var showPurchasePlans = false

    var body: some View {
        List {
            Section {
                NavigationLink {
                    ThemePickerView(onPremiumActivated: { dismiss() })
                        .environmentObject(themeStore)
                        .analyticsScreen(.feedThemes, flowID: "feed")
                } label: {
                    HStack {
                        Label(String(localized: "settings_theme"), systemImage: "paintpalette")
                        Spacer()
                        Text(themeStore.selected.displayName)
                            .foregroundStyle(.secondary)
                    }
                }
                .accessibilityIdentifier("settings-theme")

                NavigationLink {
                    NotificationsSettingsView()
                        .analyticsScreen(.feedReminders, flowID: "feed")
                } label: {
                    Label(String(localized: "settings_notifications"), systemImage: "bell")
                }

                NavigationLink {
                    LikedQuotesView()
                        .environmentObject(likedStore)
                        .analyticsScreen(.feedSaved, flowID: "feed")
                } label: {
                    HStack {
                        Label(String(localized: "settings_liked_quotes"), systemImage: "heart")
                        Spacer()
                        Text("\(likedStore.likedIds.count)")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .listRowBackground(AppTheme.Colors.cardBackground.opacity(0.8))

            Section {
                Button {
                    showPurchasePlans = true
                } label: {
                    Label(String(localized: "settings_subscription_subscribe"), systemImage: "star.circle")
                }
                .accessibilityIdentifier("settings-subscribe")

                NavigationLink {
                    RevenueCatUI.CustomerCenterView()
                        .navigationTitle(String(localized: "settings_subscription"))
                        .navigationBarTitleDisplayMode(.inline)
                        .analyticsScreen(.settingsSubscription, flowID: "settings")
                } label: {
                    Label(String(localized: "settings_subscription"), systemImage: "creditcard")
                }
            }
            .listRowBackground(AppTheme.Colors.cardBackground.opacity(0.8))

            Section {
                Button(role: .destructive) {
                    showSignOutConfirmation = true
                } label: {
                    Label(String(localized: "settings_sign_out"), systemImage: "rectangle.portrait.and.arrow.right")
                }
            }
            .listRowBackground(AppTheme.Colors.cardBackground.opacity(0.8))
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(AppBackground())
        .foregroundStyle(AppTheme.Colors.label)
        .affirmationNavigationTitle(String(localized: "settings_title"))
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(String(localized: "common_done")) { dismiss() }
                    .accessibilityIdentifier("settings-done")
            }
        }
        .fullScreenCover(isPresented: $showPurchasePlans) {
            PaywallFlowContainer(
                onPurchaseSuccess: { customerInfo in
                    AppState.shared.updateSubscriptionInfo(from: customerInfo)
                    showPurchasePlans = false
                    AnalyticsManager.shared.trackScreenViewedIfNeeded(screenID: .feedSettings, flowID: "feed")
                },
                onDismiss: {
                    showPurchasePlans = false
                    AnalyticsManager.shared.trackScreenViewedIfNeeded(screenID: .feedSettings, flowID: "feed")
                },
                flowID: "settings_subscription"
            )
            .environmentObject(AppState.shared)
        }
        .confirmationDialog(String(localized: "settings_sign_out"), isPresented: $showSignOutConfirmation, titleVisibility: .visible) {
            Button(String(localized: "common_sign_out"), role: .destructive) {
                AppState.shared.signOutPreservingSensorAccess()
                dismiss()
            }
            Button(String(localized: "common_cancel"), role: .cancel) {}
        }
    }
}

/// 8 theme grid. Tap = select + persist + dismiss.
struct ThemePickerView: View {
    var onPremiumActivated: (() -> Void)? = nil
    @EnvironmentObject var themeStore: ThemeStore
    @Environment(\.dismiss) private var dismiss

    @ObservedObject private var appState = AppState.shared
    @State private var pendingTheme: ThemeID?
    @State private var showThemePaywall = false

    private let columns = [GridItem(.flexible()), GridItem(.flexible())]
    private var orderedThemes: [ThemeID] {
        [themeStore.selected] + ThemeID.allCases.filter { $0 != themeStore.selected }
    }

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 16) {
                ForEach(orderedThemes) { theme in
                    Button {
                        if theme.isAvailable(isEntitled: appState.subscriptionInfo.isEntitled) {
                            themeStore.select(theme)
                            dismiss()
                        } else {
                            pendingTheme = theme
                            showThemePaywall = true
                        }
                    } label: {
                        ZStack(alignment: .bottomLeading) {
                            Color.clear.frame(height: 220)
                                .overlay { theme.image.resizable().scaledToFill() }
                                .clipped()
                            LinearGradient(colors: [.clear, .black.opacity(0.7)], startPoint: .center, endPoint: .bottom)
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Spacer()
                                    if themeStore.selected == theme {
                                        Image(systemName: "checkmark.circle.fill")
                                            .font(.title2)
                                            .foregroundStyle(.white)
                                            .padding(4)
                                            .background(AppTheme.Colors.accent, in: Circle())
                                            .accessibilityLabel(String(localized: "growth_theme_selected"))
                                            .accessibilityIdentifier("theme-selected-\(theme.rawValue)")
                                    }
                                }
                                Spacer()
                                Text(theme.displayName)
                                    .font(.system(.headline, design: .serif))
                                    .fixedSize(horizontal: false, vertical: true)
                                if !theme.isAvailable(isEntitled: appState.subscriptionInfo.isEntitled) {
                                    Label(String(localized: "growth_theme_premium"), systemImage: "lock.fill")
                                        .font(.caption)
                                }
                            }
                            .foregroundStyle(.white)
                            .padding(12)
                        }
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                        .overlay {
                            RoundedRectangle(cornerRadius: 16)
                                .strokeBorder(themeStore.selected == theme ? AppTheme.Colors.accent : .clear, lineWidth: 2)
                        }
                    }
                    .accessibilityIdentifier("theme-\(theme.rawValue)")
                    .accessibilityLabel(theme.displayName)
                    .accessibilityAddTraits(themeStore.selected == theme ? .isSelected : [])
                    .accessibilityElement(children: .contain)
                    .buttonStyle(.plain)
                }
            }
            .padding(16)
        }
        .background(AppBackground())
        .affirmationNavigationTitle(String(localized: "settings_theme"))
        .fullScreenCover(isPresented: $showThemePaywall) {
            PaywallFlowContainer(
                onPurchaseSuccess: { customerInfo in
                    appState.updateSubscriptionInfo(from: customerInfo)
                    guard appState.subscriptionInfo.isEntitled else { return }
                    if let pendingTheme { themeStore.select(pendingTheme) }
                    pendingTheme = nil
                    showThemePaywall = false
                    if let onPremiumActivated {
                        onPremiumActivated()
                    } else {
                        dismiss()
                    }
                },
                onDismiss: {
                    pendingTheme = nil
                    showThemePaywall = false
                    AnalyticsManager.shared.trackScreenViewedIfNeeded(screenID: .feedThemes, flowID: "feed")
                },
                flowID: "premium_theme"
            )
            .environmentObject(appState)
        }
    }
}

/// Each saved affirmation keeps the background it had when it was liked.
struct LikedQuotesView: View {
    @EnvironmentObject var likedStore: LikedQuotesStore

    var likedQuotes: [Quote] {
        likedStore.savedQuotes(in: QuoteProvider.shared.all(preferredLanguage: AppState.shared.effectiveLanguage))
    }

    var body: some View {
        Group {
            if likedQuotes.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "heart")
                        .font(.system(size: 44))
                        .foregroundStyle(.secondary)
                    Text(String(localized: "liked_empty_title"))
                        .font(.system(.title2, design: .serif))
                    Text(String(localized: "liked_empty_subtitle"))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding(40)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 16) {
                        ForEach(likedQuotes) { quote in
                            let theme = ThemeID(rawValue: likedStore.themeID(for: quote.id)) ?? .sageMist
                            Text(quote.text)
                                .font(.system(.title2, design: .serif))
                                .foregroundStyle(theme.foregroundColor)
                                .multilineTextAlignment(.center)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(24)
                                .frame(maxWidth: .infinity, minHeight: 220)
                                .background {
                                    GeometryReader { geo in
                                        theme.image.resizable().scaledToFill()
                                            .frame(width: geo.size.width, height: geo.size.height)
                                            .clipped()
                                    }
                                }
                                .clipShape(RoundedRectangle(cornerRadius: 16))
                                .accessibilityIdentifier("liked-quote-\(quote.id)")
                        }
                    }
                    .padding(24)
                }
            }
        }
        .background(AppBackground())
        .foregroundStyle(AppTheme.Colors.label)
        .affirmationNavigationTitle(String(localized: "settings_liked_quotes"))
    }
}

/// Shows the saved delivery configuration and OS permission separately.
struct NotificationsSettingsView: View {
    @ObservedObject private var appState = AppState.shared
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var scenePhase
    @State private var notificationsAllowed = false
    @State private var isUpdatingPermission = false
    private let permissionLogger = Logger(subsystem: "com.anicca.ios", category: "NotificationSettings")

    private var slots: [String] {
        let user = appState.syntheticUser
        if user.hasAdaptiveAnswers || !(user.receptivityWindows["reminder_slots"] ?? []).isEmpty {
            return PersonalizationRules.effectiveSlots(user: user).map { $0.label }
        }
        return ReminderSchedule.slots(isPro: appState.subscriptionInfo.isEntitled)
    }

    var body: some View {
        Form {
            Section {
                HStack {
                    Text(String(localized: "notifications_daily_count"))
                    Spacer()
                    Text("\(slots.count)")
                        .foregroundStyle(.secondary)
                }
                ForEach(slots, id: \.self) { time in Text(time).monospacedDigit() }

                Text(String(localized: notificationsAllowed ? "growth_notifications_on" : "growth_notifications_off"))
                    .accessibilityIdentifier("reminder-permission-status")
                PrimaryButton(title: String(localized: "growth_notification_settings"), isEnabled: !isUpdatingPermission) {
                    permissionLogger.notice("permission tap busy=\(isUpdatingPermission, privacy: .public)")
                    guard !isUpdatingPermission else { return }
                    isUpdatingPermission = true
                    Task { @MainActor in
                        defer { isUpdatingPermission = false }
                        let settings = await UNUserNotificationCenter.current().notificationSettings()
                        permissionLogger.notice("permission prior status=\(settings.authorizationStatus.rawValue, privacy: .public)")
                        if settings.authorizationStatus == .notDetermined {
                            AnalyticsManager.shared.track(.notificationPermissionRequested, properties: ["source": "settings"])
                            _ = await NotificationScheduler.shared.requestAuthorizationIfNeeded()
                            notificationsAllowed = await NotificationScheduler.shared.isAuthorizedForAlerts()
                            permissionLogger.notice("permission prompt completed alerts=\(notificationsAllowed, privacy: .public)")
                            AnalyticsManager.shared.track(.notificationPermissionResult, properties: ["source": "settings", "result": notificationsAllowed ? "allowed" : "denied"])
                            if notificationsAllowed { UIApplication.shared.registerForRemoteNotifications() }
                            // A permission choice finishes here. Opening Settings is
                            // a separate, explicit action after permission is settled.
                            return
                        }
                        permissionLogger.notice("permission opening system settings")
                        if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                    }
                }
                .disabled(isUpdatingPermission)
                .accessibilityIdentifier("reminder-enable-notifications")
            } footer: {
                Text(String(localized: "growth_reminder_explanation"))
                    .fixedSize(horizontal: false, vertical: true)
            }
            .listRowBackground(AppTheme.Colors.cardBackground.opacity(0.8))
        }
        .scrollContentBackground(.hidden)
        .background(AppBackground())
        .foregroundStyle(AppTheme.Colors.label)
        .affirmationNavigationTitle(String(localized: "settings_notifications"))
        .task { notificationsAllowed = await NotificationScheduler.shared.isAuthorizedForAlerts() }
        .onChange(of: scenePhase) { phase in
            if phase == .active { Task { notificationsAllowed = await NotificationScheduler.shared.isAuthorizedForAlerts() } }
        }
    }
}
