import ActivityKit
import WidgetKit
import SwiftUI

struct AniccaWidgetAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var emoji: String
    }
    var name: String
}

struct AniccaWidgetLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: AniccaWidgetAttributes.self) { context in
            VStack(alignment: .leading, spacing: 8) {
                Text("Anicca")
                    .font(.system(.headline, design: .serif))
                    .foregroundStyle(WidgetAppearance.accent)
                Text(context.attributes.name)
                    .font(.system(.body, design: .serif))
                    .fixedSize(horizontal: false, vertical: true)
                    .foregroundStyle(WidgetAppearance.label)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(20)
            .activityBackgroundTint(WidgetAppearance.background)
            .activitySystemActionForegroundColor(WidgetAppearance.accent)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text("Anicca").font(.system(.headline, design: .serif))
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text(context.state.emoji)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text(context.attributes.name)
                        .font(.system(.body, design: .serif))
                        .fixedSize(horizontal: false, vertical: true)
                }
            } compactLeading: {
                Image(systemName: "sun.max")
            } compactTrailing: {
                Text(context.state.emoji)
            } minimal: {
                Image(systemName: "sun.max")
            }
            .widgetURL(URL(string: "anicca://"))
            .keylineTint(WidgetAppearance.accent)
        }
    }
}

#if swift(>=5.9)
@available(iOS 17.0, *)
#Preview("Affirmation", as: .content, using: AniccaWidgetAttributes(name: "Be kind to yourself.")) {
    AniccaWidgetLiveActivity()
} contentStates: {
    AniccaWidgetAttributes.ContentState(emoji: "🪷")
}
#endif
