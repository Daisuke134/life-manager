"""Exercise the real SwiftUI sign-out actions without starting the iOS app."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


VIEW = Path(__file__).resolve().parents[2] / "aniccaios/Views/Feed/SettingsSheet.swift"


def action(source, marker):
    start = source.index("{", source.index(marker) + len(marker))
    depth = 1
    for end in range(start + 1, len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if depth == 0:
            return source[start + 1:end]
    raise AssertionError("Unterminated SwiftUI action")


class SettingsSignOutTests(unittest.TestCase):
    def test_confirmation_is_bound_to_the_settings_button(self):
        source = VIEW.read_text()
        self.assertIn('isPresented: $showSignOutConfirmation', source)
        self.assertIn('showSignOutConfirmation = true', action(source, 'Button(role: .destructive)'))

    @unittest.skipUnless(shutil.which("swift"), "Swift runtime is unavailable")
    def test_tap_waits_for_confirmation_cancel_is_inert_and_confirm_signs_out(self):
        source = VIEW.read_text()
        tap = action(source, 'Button(role: .destructive)')
        confirm = action(source, 'Button(String(localized: "common_sign_out"), role: .destructive)')
        cancel = action(source, 'Button(String(localized: "common_cancel"), role: .cancel)')
        fixture = '''
import Foundation
var events: [String] = []
var showSignOutConfirmation = false
final class AppState {
    static let shared = AppState()
    func signOutPreservingSensorAccess() { events.append("logout-preserving-sensors") }
}
func dismiss() { events.append("dismiss") }
func tap() { TAP }
func confirm() { CONFIRM }
func cancel() { CANCEL }
tap()
precondition(showSignOutConfirmation && events.isEmpty)
cancel()
precondition(events.isEmpty)
tap()
confirm()
precondition(events == ["logout-preserving-sensors", "dismiss"])
'''.replace('TAP', tap).replace('CONFIRM', confirm).replace('CANCEL', cancel)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SettingsSignOut.swift"
            path.write_text(fixture)
            result = subprocess.run(["swift", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
