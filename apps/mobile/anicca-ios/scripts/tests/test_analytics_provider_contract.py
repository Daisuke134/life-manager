#!/usr/bin/env python3
"""Guard Anicca's single-provider analytics and screen/purchase event contract."""

from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "aniccaios"
PROJECT = ROOT / "aniccaios.xcodeproj" / "project.pbxproj"
RESOLVED = ROOT / "aniccaios.xcodeproj" / "project.xcworkspace" / "xcshareddata" / "swiftpm" / "Package.resolved"
CALLERS = {
    "onboarding": APP / "Onboarding" / "OnboardingFlowView.swift",
    "paywall": APP / "Onboarding" / "OnboardingBibleViews.swift",
    "feed": APP / "Views" / "Feed" / "FeedRootView.swift",
    "permission": APP / "Onboarding" / "NotificationPermissionStepView.swift",
    "push_registration": APP / "Services" / "PushTokenService.swift",
    "active_paywall": APP / "Onboarding" / "PaywallVariantBView.swift",
    "legacy_paywall": APP / "Onboarding" / "PlanSelectionStepView.swift",
    "retention_offer": APP / "Onboarding" / "RetentionOfferSheet.swift",
}


def main() -> int:
    swift = {path: path.read_text() for path in APP.rglob("*.swift")}
    project = PROJECT.read_text()
    package_lock = RESOLVED.read_text()
    package_and_project = project + package_lock

    posthog = [str(path.relative_to(ROOT)) for path, source in swift.items() if "PostHog" in source]
    if posthog or "posthog-ios" in package_and_project or "POSTHOG_" in package_and_project:
        raise AssertionError(f"PostHog must not remain in the iOS analytics path: {posthog}")

    resolved = json.loads(package_lock)
    mixpanel = [p["state"] for p in resolved["pins"] if p["identity"] == "mixpanel-swift"]
    if (
        len(mixpanel) != 1
        or mixpanel[0].get("version") != "7.1.0"
        or mixpanel[0].get("revision") != "38e63de7d71a2b6787bbd190ef8fcc04d053f259"
        or 'kind = exactVersion;' not in project
        or 'version = 7.1.0;' not in project
        or 'branch = master;' in project
    ):
        raise AssertionError(f"Mixpanel Swift SDK must use the verified stable 7.1.0 pin: {mixpanel}")

    manager = swift[APP / "Services" / "AnalyticsManager.swift"]
    required_contract = (
        'case screenViewed = "screen_viewed"',
        'case screenExited = "screen_exited"',
        'case onboardingStepViewed = "onboarding_step_viewed"',
        'case onboardingStepCompleted = "onboarding_step_completed"',
        'case notificationPermissionRequested = "notification_permission_requested"',
        'case notificationRegistrationResult = "notification_registration_result"',
        'case purchaseStarted = "purchase_started"',
        'case purchaseResult = "purchase_result"',
        'case restoreStarted = "restore_started"',
        'case restoreResult = "restore_result"',
        '"event_id"',
        '"event_timestamp"',
        '"screen_instance_id"',
        '"flow_id"',
        '"locale"',
        '"storefront_country_code"',
        '"device_region_code"',
        'private var screenVisits = ScreenVisitLedger()',
        'screenVisits.enter(',
        'screenVisits.exit(',
        'screenVisits.suspend()',
        'screenVisits.resume(',
        'screenVisits.resetSession()',
        'func suspendCurrentScreenVisit()',
        'func resumeCurrentScreenVisit()',
    )
    for marker in required_contract:
        if marker not in manager:
            raise AssertionError(f"Missing analytics contract: {marker}")

    app_delegate = (APP / "AppDelegate.swift").read_text()
    became_active = app_delegate.split("func applicationDidBecomeActive", 1)[1].split(
        "func applicationDidEnterBackground", 1
    )[0]
    if "AnalyticsManager.shared.resumeCurrentScreenVisit()" not in became_active:
        raise AssertionError("Foreground resume must reopen the suspended screen visit")

    screen_modifier = manager.split("private struct AnalyticsScreenModifier", 1)[1].split("extension View", 1)[0]
    if "trackScreenViewedIfNeeded(screenID: screenID, flowID: flowID)" not in screen_modifier:
        raise AssertionError("SwiftUI appearance must not duplicate a visit already resumed by the app lifecycle")

    onboarding = CALLERS["onboarding"].read_text()
    onboarding_record = onboarding.split("private func recordStepView()", 1)[1].split("private func advance()", 1)[0]
    if "trackScreenViewedIfNeeded(screenID: screenID, flowID: \"onboarding\")" not in onboarding_record:
        raise AssertionError("Onboarding appearance must deduplicate a screen visit resumed by the app lifecycle")
    if "trackScreenViewed(screenID:" in onboarding_record:
        raise AssertionError("Onboarding must not force a duplicate exit when the same step reappears")

    reset_body = manager.split("func reset() {", 1)[1].split("\n    }", 1)[0]
    if "screenVisits.resetSession()" not in reset_body:
        raise AssertionError("Analytics reset must clear visits and rotate the session identity")

    for unsafe in ('"displayed_price"', '"amount_source"', '"transaction_id"', '"transaction_id_hash"'):
        if unsafe in manager:
            raise AssertionError(f"Client-only price/transaction values must not be sent: {unsafe}")

    required_screens = {
        "onboarding.welcome", "onboarding.goal", "onboarding.name", "onboarding.pain_points",
        "onboarding.struggle_frequency", "onboarding.reminder_schedule",
        "onboarding.birth_context", "onboarding.mood_baseline", "onboarding.belief_themes",
        "onboarding.tone", "onboarding.life_context", "onboarding.routine_anchors",
        "onboarding.prior_attempts", "onboarding.prior_helpfulness", "onboarding.start_reason",
        "onboarding.quiet_hours", "onboarding.stress_trigger", "onboarding.anxiety_target",
        "onboarding.self_criticism", "onboarding.avoidance_task", "onboarding.sleep_reason",
        "onboarding.bedtime", "onboarding.wake_time",
        "onboarding.processing", "onboarding.first_affirmation",
        "onboarding.comparison", "onboarding.notifications", "paywall",
        "paywall.retention_offer", "feed", "feed.collections", "feed.saved",
        "feed.reminders", "feed.themes", "feed.settings", "settings.subscription",
    }
    inventory_source = manager
    missing = sorted(screen for screen in required_screens if f'"{screen}"' not in inventory_source)
    if missing:
        raise AssertionError(f"Analytics screen inventory is incomplete: {missing}")

    required_callers = {
        "onboarding": ("onboardingStepCompleted", "trackScreenViewed", "onboardingStepViewed"),
        "paywall": ("analyticsScreen(.paywall",),
        "feed": ("analyticsScreen(.feed", "affirmationViewed", "trackScreenViewed"),
        "permission": ("notificationPermissionRequested",),
        "push_registration": ("notificationRegistrationResult",),
        "active_paywall": ("trackPurchaseStarted", "trackRestoreStarted", "trackRestoreResult"),
        "legacy_paywall": ("PaywallVariantBView(", 'flowID: "legacy_paywall"', "onPurchaseSuccess: onPurchaseSuccess"),
        "retention_offer": ("trackPurchaseStarted", "trackPurchaseResult"),
    }
    missing_callers = {
        name: [marker for marker in markers if marker not in CALLERS[name].read_text()]
        for name, markers in required_callers.items()
    }
    missing_callers = {name: markers for name, markers in missing_callers.items() if markers}
    if missing_callers:
        raise AssertionError(f"Analytics event contract is not wired to all active call sites: {missing_callers}")

    print("analytics provider contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"analytics provider contract: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
