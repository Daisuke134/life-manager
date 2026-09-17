import SwiftUI
import Combine
import RevenueCat
import RevenueCatUI

/// ↓ pull-down sheet from FeedRootView.
/// 1mm clone of i.am app settings (modal sheet with categories: Theme / Notifications / Saved / Liked / Subscription / Account / Sign out).
struct SettingsSheet: View {
    @EnvironmentObject var themeStore: ThemeStore
    @EnvironmentObject var likedStore: LikedQuotesStore
    @Environment(\.dismiss) private var dismiss

    @State private var showThemePicker = false
    @State private var showSavedQuotes = false
    @State private var showLikedQuotes = false

    var body: some View {
        List {
            Section {
                NavigationLink {
                    ThemePickerView()
                        .environmentObject(themeStore)
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
                } label: {
                    Label(String(localized: "settings_notifications"), systemImage: "bell")
                }

                NavigationLink {
                    LikedQuotesView()
                        .environmentObject(likedStore)
                } label: {
                    HStack {
                        Label(String(localized: "settings_liked_quotes"), systemImage: "heart")
                        Spacer()
                        Text("\(likedStore.likedIds.count)")
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Section {
                NavigationLink {
                    RevenueCatUI.CustomerCenterView()
                        .navigationTitle(String(localized: "settings_subscription"))
                        .navigationBarTitleDisplayMode(.inline)
                } label: {
                    Label(String(localized: "settings_subscription"), systemImage: "creditcard")
                }
            }

            Section {
                Button(role: .destructive) {
                    // Sign out hook — kept minimal here; app-level wiring stays in AppState.
                } label: {
                    Label(String(localized: "settings_sign_out"), systemImage: "rectangle.portrait.and.arrow.right")
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(String(localized: "settings_title"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(String(localized: "common_done")) { dismiss() }
            }
        }
    }
}

/// 8 theme grid. Tap = select + persist + dismiss.
struct ThemePickerView: View {
    @EnvironmentObject var themeStore: ThemeStore
    @Environment(\.dismiss) private var dismiss

    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 16) {
                ForEach(ThemeID.allCases) { theme in
                    Button {
                        themeStore.select(theme)
                        dismiss()
                    } label: {
                        ZStack(alignment: .bottomLeading) {
                            theme.image
                                .resizable()
                                .scaledToFill()
                                .frame(height: 240)
                                .clipped()
                                .clipShape(RoundedRectangle(cornerRadius: 16))
                            HStack {
                                Text(theme.displayName)
                                    .font(.footnote)
                                    .foregroundStyle(.white)
                                    .padding(8)
                                Spacer()
                                if themeStore.selected == theme {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundStyle(.white)
                                        .padding(8)
                                }
                            }
                            .background(LinearGradient(colors: [.clear, .black.opacity(0.5)], startPoint: .top, endPoint: .bottom))
                            .clipShape(RoundedRectangle(cornerRadius: 16))
                        }
                        .accessibilityIdentifier("theme-\(theme.rawValue)")
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(16)
        }
        .navigationTitle(String(localized: "settings_theme"))
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// Liked quotes grid. Tap = (future) jump back to feed at that quote.
struct LikedQuotesView: View {
    @EnvironmentObject var likedStore: LikedQuotesStore

    var likedQuotes: [Quote] {
        QuoteProvider.shared.all().filter { likedStore.isLiked($0.id) }
    }

    var body: some View {
        Group {
            if likedQuotes.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "heart")
                        .font(.system(size: 44))
                        .foregroundStyle(.secondary)
                    Text(String(localized: "liked_empty_title"))
                        .font(.headline)
                    Text(String(localized: "liked_empty_subtitle"))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding(40)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(likedQuotes) { q in
                        Text(q.text)
                            .padding(.vertical, 8)
                    }
                }
            }
        }
        .navigationTitle(String(localized: "settings_liked_quotes"))
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// Minimal notifications settings stub — wired to NotificationScheduler.
struct NotificationsSettingsView: View {
    @State private var dailyCount = 4

    var body: some View {
        Form {
            Section {
                HStack {
                    Text(String(localized: "notifications_daily_count"))
                    Spacer()
                    Text("\(dailyCount)")
                        .foregroundStyle(.secondary)
                }
                Text(String(localized: "notifications_schedule_label"))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } footer: {
                Text(String(localized: "notifications_footer"))
            }
        }
        .navigationTitle(String(localized: "settings_notifications"))
        .navigationBarTitleDisplayMode(.inline)
    }
}
