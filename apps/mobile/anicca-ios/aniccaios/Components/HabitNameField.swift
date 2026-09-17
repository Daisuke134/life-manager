import SwiftUI

struct HabitNameField: View {
    @Binding var text: String
    @FocusState var isFocused: Bool

    var body: some View {
        TextField(String(localized: "habit_custom_name_placeholder"), text: $text)
            .textInputAutocapitalization(.sentences)
            .disableAutocorrection(true)
            .focused($isFocused)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(RoundedRectangle(cornerRadius: 10).stroke(Color(uiColor: .separator)))
            .onSubmit { isFocused = false }
    }
}


