import WidgetKit
import SwiftUI

// MARK: - Entry

struct NudgeEntry: TimelineEntry {
    let date: Date
    let nudgeText: String
    let problemEmoji: String
}

// MARK: - Provider

struct NudgeTimelineProvider: TimelineProvider {
    private var fallbackText: String {
        let preferred = Locale.preferredLanguages.first ?? "en"
        if preferred.hasPrefix("ja") { return "自分に優しくしよう。" }
        if preferred.hasPrefix("es") { return "Sé amable contigo mismo." }
        return "Be kind to yourself."
    }

    func placeholder(in context: Context) -> NudgeEntry {
        NudgeEntry(date: Date(), nudgeText: fallbackText, problemEmoji: "🪷")
    }

    func getSnapshot(in context: Context, completion: @escaping (NudgeEntry) -> Void) {
        let entry = makeEntry(for: Date())
        completion(entry)
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<NudgeEntry>) -> Void) {
        var entries: [NudgeEntry] = []
        let calendar = Calendar.current
        let now = Date()

        for dayOffset in 0..<7 {
            guard let date = calendar.date(byAdding: .day, value: dayOffset, to: calendar.startOfDay(for: now)) else { continue }
            entries.append(makeEntry(for: date))
        }

        completion(Timeline(entries: entries, policy: .atEnd))
    }

    private func makeEntry(for date: Date) -> NudgeEntry {
        let struggles = NudgeWidgetDataStore.loadStruggles()
        let texts = NudgeWidgetDataStore.loadTexts()
        let dayOfYear = Calendar.current.ordinality(of: .day, in: .year, for: date) ?? 1

        guard !struggles.isEmpty else {
            return NudgeEntry(date: date, nudgeText: fallbackText, problemEmoji: "🪷")
        }

        let problemKey = struggles[dayOfYear % struggles.count]
        let problemTexts = texts[problemKey] ?? []
        let text = problemTexts.isEmpty ? fallbackText : problemTexts[dayOfYear % problemTexts.count]
        let emoji = ProblemType(rawValue: problemKey)?.icon ?? "🪷"

        return NudgeEntry(date: date, nudgeText: text, problemEmoji: emoji)
    }
}

// MARK: - Views

struct NudgeWidgetSmallView: View {
    let entry: NudgeEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(entry.problemEmoji)
                .font(.title2)

            Spacer()

            Text(entry.nudgeText)
                .font(.system(size: 14, weight: .semibold))
                .lineLimit(4)
                .minimumScaleFactor(0.8)

            Text("— Anicca")
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
        }
        .padding()
    }
}

struct NudgeWidgetMediumView: View {
    let entry: NudgeEntry

    var body: some View {
        HStack(spacing: 16) {
            Text(entry.problemEmoji)
                .font(.system(size: 36))

            VStack(alignment: .leading, spacing: 4) {
                Text(entry.nudgeText)
                    .font(.system(size: 15, weight: .semibold))
                    .lineLimit(3)
                    .minimumScaleFactor(0.8)

                Text("— Anicca 🪷")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding()
    }
}

struct NudgeWidgetLockScreenView: View {
    let entry: NudgeEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(entry.nudgeText)
                .font(.system(size: 12, weight: .medium))
                .lineLimit(2)
                .minimumScaleFactor(0.8)
        }
    }
}

// MARK: - Widget

struct AniccaWidget: Widget {
    let kind = "AniccaWidget"

    private var widgetDescription: String {
        let preferred = Locale.preferredLanguages.first ?? "en"
        if preferred.hasPrefix("ja") { return "毎日届く、あなたへの言葉" }
        if preferred.hasPrefix("es") { return "Sabiduría diaria para tu crecimiento" }
        return "Daily wisdom for your growth"
    }

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: NudgeTimelineProvider()) { entry in
            if #available(iOS 17.0, *) {
                NudgeWidgetEntryView(entry: entry)
                    .containerBackground(.fill.tertiary, for: .widget)
            } else {
                NudgeWidgetEntryView(entry: entry)
            }
        }
        .configurationDisplayName("Anicca")
        .description(widgetDescription)
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryRectangular])
    }
}

struct NudgeWidgetEntryView: View {
    @Environment(\.widgetFamily) var family
    let entry: NudgeEntry

    var body: some View {
        switch family {
        case .systemSmall:
            NudgeWidgetSmallView(entry: entry)
        case .systemMedium:
            NudgeWidgetMediumView(entry: entry)
        case .accessoryRectangular:
            NudgeWidgetLockScreenView(entry: entry)
        default:
            NudgeWidgetSmallView(entry: entry)
        }
    }
}
