import ComponentsKit
import SwiftUI
import UserNotifications
import UIKit

struct NotificationPermissionStepView: View {
    let next: () -> Void

    @State private var notificationGranted = false
    @State private var notificationDenied = false
    @State private var isRequesting = false
    @State private var hasAttemptedPermission = false

    private let timeSlots: [(icon: String, key: String)] = [
        ("sunrise.fill", "onboarding_notifications_morning"),
        ("sun.max.fill", "onboarding_notifications_midday"),
        ("moon.fill", "onboarding_notifications_evening")
    ]

    var body: some View {
        VStack(spacing: 24) {
            Text(String(localized: "onboarding_notifications_title"))
                .font(.system(size: 32, weight: .bold))
                .foregroundStyle(AppTheme.Colors.label)
                .padding(.top, 40)

            Text(String(localized: "onboarding_notifications_description"))
                .font(.system(size: 16))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            // Value framing: show what notifications deliver
            VStack(spacing: 12) {
                ForEach(timeSlots, id: \.key) { slot in
                    HStack(spacing: 12) {
                        Image(systemName: slot.icon)
                            .font(.system(size: 20))
                            .foregroundStyle(AppTheme.Colors.accent)
                            .frame(width: 28)

                        Text(String(localized: String.LocalizationValue(slot.key)))
                            .font(.system(size: 16, weight: .medium))
                            .foregroundStyle(AppTheme.Colors.label)

                        Spacer()
                    }
                    .padding(.horizontal, 32)
                }
            }
            .padding(.top, 8)

            Spacer()

            Button {
                if hasAttemptedPermission {
                    next()
                } else {
                    requestNotifications()
                }
            } label: {
                if isRequesting {
                    ProgressView()
                        .tint(.white)
                        .frame(maxWidth: .infinity)
                        .frame(height: 56)
                        .background(AppTheme.Colors.accent)
                        .clipShape(RoundedRectangle(cornerRadius: 28))
                } else {
                    Text(hasAttemptedPermission ? String(localized: "common_continue") : String(localized: "onboarding_notifications_allow"))
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .frame(height: 56)
                        .background(hasAttemptedPermission ? AppTheme.Colors.buttonSelected : AppTheme.Colors.accent)
                        .clipShape(RoundedRectangle(cornerRadius: 28))
                }
            }
            .disabled(isRequesting)
            .accessibilityIdentifier("onboarding-notifications-allow")
            .padding(.horizontal, 24)
            .padding(.bottom, 64)
        }
        .background(AppBackground())
        .onAppear {
            Task { await refreshAuthorizationState(autoAdvance: false) }
        }
    }

    private func requestNotifications() {
        guard !isRequesting else { return }
        isRequesting = true
        Task {
            let granted = await NotificationScheduler.shared.requestAuthorization()
            await MainActor.run {
                notificationGranted = granted
                notificationDenied = !granted
                isRequesting = false
                hasAttemptedPermission = true
                if granted {
                    // v1.8.7: notifications are remote-only (APNs). Register now that
                    // the user granted permission so the device token reaches the backend.
                    UIApplication.shared.registerForRemoteNotifications()
                }
                next()
            }
        }
    }

    private func refreshAuthorizationState(autoAdvance: Bool) async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        await MainActor.run {
            let authorized = settings.authorizationStatus == .authorized
                || settings.authorizationStatus == .provisional
                || settings.authorizationStatus == .ephemeral
            let timeSensitiveOk = settings.timeSensitiveSetting != .disabled
            notificationGranted = authorized && timeSensitiveOk
            notificationDenied = settings.authorizationStatus == .denied
        }
    }

    private func openSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        UIApplication.shared.open(url)
    }
}
