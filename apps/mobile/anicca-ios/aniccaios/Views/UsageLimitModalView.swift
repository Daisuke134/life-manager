import SwiftUI

struct UsageLimitModalView: View {
    let plan: SubscriptionInfo.Plan
    let reason: AppState.QuotaHoldReason
    let onClose: () -> Void
    let onUpgrade: () -> Void
    let onManage: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                Text(title)
                    .font(AppTheme.Typography.title2Dynamic)
                    .accessibilityAddTraits(.isHeader)
                Text(message)
                    .font(.subheadline)
                    .foregroundStyle(AppTheme.Colors.secondaryLabel)
                if plan == .free {
                    PrimaryButton(title: upgradeButtonText, action: onUpgrade)
                } else {
                    PrimaryButton(title: manageButtonText, action: onManage)
                }
                Button(closeButtonText, action: onClose)
                    .frame(minHeight: 44)
                    .tint(AppTheme.Colors.accent)
            }
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .foregroundStyle(AppTheme.Colors.label)
            .padding(24)
        }
        .background(AppBackground())
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
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

