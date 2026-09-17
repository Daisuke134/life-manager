import SwiftUI

struct HabitSleepFollowUpView: View {
    let onRegisterSave: ((@escaping () -> Void) -> Void)?
    @EnvironmentObject private var appState: AppState
    @State private var sleepLocation: String = ""
    @State private var routines: [RoutineItem] = [
        RoutineItem(text: ""),
        RoutineItem(text: ""),
        RoutineItem(text: "")
    ]
    
    init(onRegisterSave: ((@escaping () -> Void) -> Void)? = nil) {
        self.onRegisterSave = onRegisterSave
    }
    
    var body: some View {
        List {
            Section(String(localized: "habit_sleep_location")) {
                TextField(String(localized: "habit_sleep_location_placeholder"), text: $sleepLocation)
            }
            
            Section(String(localized: "habit_sleep_routines")) {
                ForEach(routines) { routine in
                    HStack {
                        // ドラッグハンドル（iOS標準の三本線アイコン）
                        Image(systemName: "line.3.horizontal")
                            .foregroundColor(.secondary)
                            .padding(.trailing, 8)
                        
                        if let index = routines.firstIndex(where: { $0.id == routine.id }) {
                            Text("\(index + 1).")
                                .frame(width: 30)
                            TextField(String(localized: "habit_routine_placeholder"), text: Binding(
                                get: { routines[index].text },
                                set: { routines[index].text = $0 }
                            ))
                        }
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) {
                            if let index = routines.firstIndex(where: { $0.id == routine.id }) {
                                routines.remove(at: index)
                            }
                        } label: {
                            Label(String(localized: "common_delete"), systemImage: "trash")
                        }
                    }
                }
                .onMove { indices, newOffset in
                    routines.move(fromOffsets: indices, toOffset: newOffset)
                }
                
                Button(action: { routines.append(RoutineItem(text: "")) }) {
                    HStack {
                        Image(systemName: "plus.circle.fill")
                        Text(String(localized: "habit_add_routine"))
                    }
                }
            }
        }
        .toolbar {
            EditButton() // onMove UIを有効化
        }
        .onAppear {
            sleepLocation = appState.userProfile.sleepLocation
            let savedRoutines = appState.userProfile.sleepRoutines
            if savedRoutines.isEmpty {
                routines = [
                    RoutineItem(text: ""),
                    RoutineItem(text: ""),
                    RoutineItem(text: "")
                ]
            } else {
                routines = savedRoutines.map { RoutineItem(text: $0) }
                if routines.count < 3 {
                    routines.append(contentsOf: Array(repeating: RoutineItem(text: ""), count: 3 - routines.count))
                }
            }
            // ルーターにsaveアクションを登録
            onRegisterSave?({ save() })
        }
    }
    
    func save() {
        appState.updateSleepLocation(sleepLocation)
        appState.updateSleepRoutines(routines.map { $0.text }.filter { !$0.isEmpty })
    }
}

