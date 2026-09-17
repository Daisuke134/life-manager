import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            Tab("翻訳", systemImage: "brain.head.profile.fill") {
                TranslateView()
            }
            Tab("履歴", systemImage: "clock.arrow.circlepath") {
                HistoryView()
            }
            Tab("設定", systemImage: "gearshape.fill") {
                SettingsView()
            }
        }
    }
}
