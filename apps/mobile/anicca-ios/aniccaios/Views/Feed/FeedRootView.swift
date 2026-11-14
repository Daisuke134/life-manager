import SwiftUI
import StoreKit

/// The home opens on one personal affirmation for today. Notifications replace it with the tapped words.
struct FeedRootView: View {
    @StateObject private var themeStore = ThemeStore()
    @StateObject private var likedStore = LikedQuotesStore()
    @ObservedObject private var appState = AppState.shared
    @StateObject private var quoteNavigation = QuoteNavigationCoordinator.shared
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var scenePhase
    @State private var quote: Quote?
    @State private var deliveryId: String?
    @State private var showSettings = false
    @State private var showSaved = false
    @State private var showReminders = false
    @State private var showThemes = false
    @State private var lastTrackedQuoteID: String?

    private var managePaymentURL: URL {
        appState.subscriptionInfo.managementURL
            ?? URL(string: "https://apps.apple.com/account/subscriptions")!
    }

    var body: some View {
        GeometryReader { geo in
            VStack(spacing: 16) {
                HStack {
                    Text(String(localized: "growth_today_for_you"))
                        .font(.system(.title2, design: .serif))
                        .fixedSize(horizontal: false, vertical: true)
                        .foregroundStyle(themeStore.selected.foregroundColor)
                        .accessibilityAddTraits(.isHeader)
                    Spacer(minLength: 8)
                    chromeButton(systemName: "paintpalette", identifier: "feed-themes") { showThemes = true }
                    chromeButton(systemName: "slider.horizontal.3", identifier: "feed-settings") { showSettings = true }
                }
                .padding(.horizontal, 24)
                .padding(.top, 8)

                if appState.subscriptionInfo.hasBillingIssue {
                    billingIssueBanner.padding(.horizontal, 24)
                }

                GeometryReader { contentGeometry in
                    ScrollView {
                        if let quote {
                            QuoteCardView(quote: quote, pageWidth: geo.size.width, deliveryId: deliveryId)
                                .frame(minHeight: contentGeometry.size.height)
                        }
                    }
                    .accessibilityIdentifier("feed-today")
                }

                HStack {
                    feedAction("growth_daily", icon: "sun.max", id: "feed-daily") { refreshToday() }
                    Spacer(minLength: 8)
                    feedAction("settings_liked_quotes", icon: "heart", id: "feed-saved") { showSaved = true }
                    Spacer(minLength: 8)
                    feedAction("settings_notifications", icon: "bell", id: "feed-reminders") { showReminders = true }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 4)
                .background(AppTheme.Colors.cardBackground.opacity(0.94), in: RoundedRectangle(cornerRadius: 18))
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
            }
            .background {
                themeStore.image.resizable().scaledToFill()
                    .frame(width: geo.size.width, height: geo.size.height + geo.safeAreaInsets.top + geo.safeAreaInsets.bottom)
                    .clipped()
                    .ignoresSafeArea()
                    .accessibilityHidden(true)
            }
        }
        .environmentObject(themeStore)
        .environmentObject(likedStore)
        .analyticsScreen(.feed, flowID: "feed")
        .onAppear { refreshToday() }
        .onChange(of: scenePhase) { phase in
            if phase == .active { refreshToday() }
        }
        .onChange(of: appState.effectiveLanguage) { _ in refreshToday() }
        .onChange(of: quoteNavigation.pendingRequest) { _ in applyPendingQuoteNavigation() }
        .sheet(isPresented: $showSaved, onDismiss: recordHomeScreen) {
            NavigationStack {
                LikedQuotesView().environmentObject(likedStore)
                    .analyticsScreen(.feedSaved, flowID: "feed")
                    .toolbar { ToolbarItem(placement: .navigationBarTrailing) { Button(String(localized: "common_close")) { showSaved = false } } }
            }
        }
        .sheet(isPresented: $showReminders, onDismiss: recordHomeScreen) {
            NavigationStack {
                NotificationsSettingsView()
                    .analyticsScreen(.feedReminders, flowID: "feed")
                    .toolbar { ToolbarItem(placement: .navigationBarTrailing) { Button(String(localized: "common_close")) { showReminders = false } } }
            }
        }
        .sheet(isPresented: $showThemes, onDismiss: recordHomeScreen) {
            NavigationStack {
                ThemePickerView().environmentObject(themeStore)
                    .analyticsScreen(.feedThemes, flowID: "feed")
                    .toolbar { ToolbarItem(placement: .navigationBarTrailing) { Button(String(localized: "common_close")) { showThemes = false } } }
            }
        }
        .sheet(isPresented: $showSettings, onDismiss: recordHomeScreen) {
            NavigationStack {
                SettingsSheet()
                    .analyticsScreen(.feedSettings, flowID: "feed")
                    .environmentObject(themeStore)
                    .environmentObject(likedStore)
            }
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
    }

    private func recordHomeScreen() {
        AnalyticsManager.shared.trackScreenViewedIfNeeded(screenID: .feed, flowID: "feed")
    }

    private func refreshToday() {
        let now = Date()
        appState.refreshSyntheticUserIfNeeded(now: now)
        let language = appState.effectiveLanguage
        let presentation = DailyAffirmationStore.shared.todayAffirmation(language: language.rawValue, now: now) {
            let user = appState.syntheticUser
            let catalog = QuoteProvider.shared.all(preferredLanguage: language)
            let band = PersonalizedNudgeSelector.TimeBand.band(forHour: Calendar.current.component(.hour, from: now))
            guard let selection = PersonalizedNudgeSelector.select(
                user: user, pool: catalog,
                shownAt: user.shownTimestamps, now: now, band: band
            ) else { return catalog.first.map { .init(quote: $0, deliveryId: nil) } }
            let origin = DecisionPointRecorder.shared.recordDecision(selection: selection, syntheticUser: user, source: "daily_home")
            return .init(quote: selection.quote, deliveryId: origin)
        }
        quote = presentation?.quote
        deliveryId = presentation?.deliveryId
        applyPendingQuoteNavigation()
        recordViewedQuoteIfNeeded()
    }

    private func applyPendingQuoteNavigation() {
        var catalog = QuoteProvider.shared.all(preferredLanguage: appState.effectiveLanguage)
        if let quote, !catalog.contains(where: { $0.id == quote.id }) { catalog.append(quote) }
        let notificationDeliveryId = quoteNavigation.pendingRequest?.deliveryId
        guard let destination = quoteNavigation.resolveQuote(in: catalog) else { return }
        quote = destination
        deliveryId = notificationDeliveryId
        DailyAffirmationStore.shared.seed(destination, language: appState.effectiveLanguage.rawValue, deliveryId: notificationDeliveryId)
        AnalyticsManager.shared.track(.notificationDestinationResolved, properties: ["quote_id": destination.id, "result": "displayed"])
        recordViewedQuoteIfNeeded()
    }

    private func recordViewedQuoteIfNeeded() {
        guard let quote, lastTrackedQuoteID != quote.id else { return }
        lastTrackedQuoteID = quote.id
        AnalyticsManager.shared.track(.affirmationViewed, properties: ["quote_id": quote.id, "category": quote.categoryID])
        let key = "anicca.feed.recent-quote-ids"
        var recent = UserDefaults.standard.stringArray(forKey: key) ?? []
        recent.removeAll { $0 == quote.id }
        recent.append(quote.id)
        UserDefaults.standard.set(Array(recent.suffix(20)), forKey: key)
    }

    private func feedAction(_ key: String, icon: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(String(localized: String.LocalizationValue(key)), systemImage: icon)
                .font(.caption)
                .foregroundStyle(AppTheme.Colors.label)
                .fixedSize(horizontal: false, vertical: true)
                .frame(minHeight: 44)
        }.accessibilityIdentifier(id)
    }

    private var billingIssueBanner: some View {
        Button {
            openURL(managePaymentURL)
        } label: {
            HStack(spacing: 10) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(.white)
                VStack(alignment: .leading, spacing: 2) {
                    Text(String(localized: "billing_issue_title"))
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.white)
                    Text(String(localized: "billing_issue_action"))
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.white.opacity(0.85))
                }
                Spacer(minLength: 8)
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.85))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color(red: 0.78, green: 0.27, blue: 0.20))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(.white.opacity(0.18), lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.3), radius: 8, y: 2)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("billing-issue-banner")
    }

    @ViewBuilder
    private func chromeButton(systemName: String, identifier: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 40, height: 40)
                .background(
                    Circle()
                        .fill(AppTheme.Colors.accent)
                )
                .overlay(
                    Circle()
                        .stroke(.white.opacity(0.25), lineWidth: 0.5)
                )
                .contentShape(Circle())

        }
        .accessibilityIdentifier(identifier)
    }
}
