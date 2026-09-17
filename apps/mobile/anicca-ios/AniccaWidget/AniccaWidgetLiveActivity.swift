//
//  AniccaWidgetLiveActivity.swift
//  AniccaWidget
//
//  Created by CBNS03 on 2025/12/07.
//

import ActivityKit
import WidgetKit
import SwiftUI

// MARK: - Live Activity
struct AniccaWidgetAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var emoji: String
    }
    var name: String
}

struct AniccaWidgetLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: AniccaWidgetAttributes.self) { context in
            VStack {
                Text("Hello \(context.state.emoji)")
            }
            .activityBackgroundTint(Color.cyan)
            .activitySystemActionForegroundColor(Color.black)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text("Leading")
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text("Trailing")
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text("Bottom \(context.state.emoji)")
                }
            } compactLeading: {
                Text("L")
            } compactTrailing: {
                Text("T \(context.state.emoji)")
            } minimal: {
                Text(context.state.emoji)
            }
            .widgetURL(URL(string: "http://www.apple.com"))
            .keylineTint(Color.red)
        }
    }
}

extension AniccaWidgetAttributes {
    fileprivate static var preview: AniccaWidgetAttributes {
        AniccaWidgetAttributes(name: "World")
    }
}

extension AniccaWidgetAttributes.ContentState {
    fileprivate static var smiley: AniccaWidgetAttributes.ContentState {
        AniccaWidgetAttributes.ContentState(emoji: "😀")
     }
     
     fileprivate static var starEyes: AniccaWidgetAttributes.ContentState {
         AniccaWidgetAttributes.ContentState(emoji: "🤩")
     }
}

// Preview を iOS 17+ に制限
#if swift(>=5.9)
@available(iOS 17.0, *)
#Preview("Notification", as: .content, using: AniccaWidgetAttributes.preview) {
   AniccaWidgetLiveActivity()
} contentStates: {
    AniccaWidgetAttributes.ContentState.smiley
    AniccaWidgetAttributes.ContentState.starEyes
}
#endif
