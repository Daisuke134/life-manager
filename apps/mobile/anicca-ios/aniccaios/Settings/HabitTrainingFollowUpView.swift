import SwiftUI

struct HabitTrainingFollowUpView: View {
    let onRegisterSave: ((@escaping () -> Void) -> Void)?
    @EnvironmentObject private var appState: AppState
    @State private var trainingGoal: String = ""
    @State private var selectedOption: String? = nil
    
    init(onRegisterSave: ((@escaping () -> Void) -> Void)? = nil) {
        self.onRegisterSave = onRegisterSave
    }
    
    var body: some View {
        Form {
            Section(String(localized: "habit_training_goal")) {
                TextField(String(localized: "habit_training_goal_placeholder"), text: $trainingGoal)
            }
            
            Section(String(localized: "habit_training_types")) {
                // ベストプラクティス: 単一選択にはPickerを使用（トグルは複数選択向け）
                Picker(String(localized: "habit_training_types"), selection: $selectedOption) {
                    Text(String(localized: "training_focus_option_pushup")).tag("Push-up" as String?)
                    Text(String(localized: "training_focus_option_core")).tag("Core" as String?)
                    Text(String(localized: "training_focus_option_cardio")).tag("Cardio" as String?)
                    Text(String(localized: "training_focus_option_stretch")).tag("Stretch" as String?)
                }
                .pickerStyle(.menu)
            }
        }
        .onAppear {
            trainingGoal = appState.userProfile.trainingGoal
            selectedOption = appState.userProfile.trainingFocus.first
            // ルーターにsaveアクションを登録
            onRegisterSave?({ save() })
        }
    }
    
    func save() {
        appState.updateTrainingGoal(trainingGoal)
        if let option = selectedOption {
            appState.updateTrainingFocus([option])
        } else {
            appState.updateTrainingFocus([])
        }
    }
}

