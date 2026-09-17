import SwiftUI

struct SectionRow: View {
    let label: String
    private let content: AnyView

    init(label: String, @ViewBuilder content: () -> some View) {
        self.label = label
        self.content = AnyView(content())
    }

    var body: some View {
        HStack {
            Text(label)
                .font(AppTheme.Typography.subheadlineDynamic)
                .foregroundStyle(AppTheme.Colors.label)
                .frame(maxWidth: .infinity, alignment: .leading)

            content
        }
        .padding(.vertical, AppTheme.Spacing.sm)
    }
}

extension SectionRow {

    static func toggle(label: String, isOn: Binding<Bool>) -> some View {
        SectionRow(label: label) {
            Toggle("", isOn: isOn)
                .labelsHidden()
        }
    }

    static func text(label: String, text: String) -> some View {
        SectionRow(label: label) {
            Text(text)
                .font(AppTheme.Typography.subheadlineDynamic)
                .foregroundStyle(AppTheme.Colors.secondaryLabel)
        }
    }

    static func button(label: String, title: String, action: @escaping () -> Void) -> some View {
        SectionRow(label: label) {
            Button(action: action) {
                HStack(spacing: 4) {
                    Text(title)
                        .font(AppTheme.Typography.subheadlineDynamic)
                    Image(systemName: "chevron.right")
                        .font(.caption)
                }
                .foregroundStyle(AppTheme.Colors.secondaryLabel)
            }
        }
    }

    static func picker<SelectionValue: Hashable, Options: View>(
        label: String,
        selection: Binding<SelectionValue>,
        @ViewBuilder content: () -> Options
    ) -> some View {
        SectionRow(label: label) {
            Picker("", selection: selection, content: content)
                .labelsHidden()
                .pickerStyle(.menu)
        }
    }
}

