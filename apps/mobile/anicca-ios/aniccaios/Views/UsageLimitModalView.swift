import SwiftUI

struct UsageLimitModalView: View {
    let plan: SubscriptionInfo.Plan
    let reason: AppState.QuotaHoldReason
    let onClose: () -> Void
    let onUpgrade: () -> Void
    let onManage: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Text(title)
                .font(.headline)
            Text(message)
                .font(.subheadline)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .padding(.horizontal)
            HStack(spacing: 12) {
                Button(closeButtonText) { onClose() }
                    .buttonStyle(.bordered)
                if plan == .free {
                    Button(upgradeButtonText) { onUpgrade() }
                        .buttonStyle(.borderedProminent)
                } else {
                    Button(manageButtonText) { onManage() }
                        .buttonStyle(.borderedProminent)
                }
            }
        }
        .padding()
        .presentationDetents([.fraction(0.35), .medium])
    }

    private var title: String {
        if reason == .sessionTimeCap {
            return NSLocalizedString("session_time_cap_title", comment: "")
        }
        switch plan {
        case .free:  return NSLocalizedString("quota_exceeded_title_free",  comment: "")
        case .pro:   return NSLocalizedString("quota_exceeded_title_pro",   comment: "")
        case .grace: return NSLocalizedString("quota_exceeded_title_grace", comment: "")
        }
    }

    private var message: String {
        if reason == .sessionTimeCap {
            return NSLocalizedString("session_time_cap_message", comment: "")
        }
        switch plan {
        case .free:  return NSLocalizedString("quota_exceeded_message_free",  comment: "")
        case .pro:   return NSLocalizedString("quota_exceeded_message_pro",   comment: "")
        case .grace: return NSLocalizedString("quota_exceeded_message_grace", comment: "")
        }
    }
    
    private var closeButtonText: String {
        NSLocalizedString("quota_exceeded_close", comment: "")
    }
    
    private var upgradeButtonText: String {
        NSLocalizedString("quota_exceeded_upgrade", comment: "")
    }
    
    private var manageButtonText: String {
        NSLocalizedString("quota_exceeded_manage", comment: "")
    }
}

