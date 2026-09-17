import SwiftUI

/// Cal AI-style processing screen with stepped progress animation.
/// Source: Smashing Magazine (Nick Babich) — "start the progressive animation slower
/// and allow it to move faster as it approaches the end. This way, you give users
/// a rapid sense of completion time."
struct ProcessingStepView: View {
    let next: () -> Void
    @EnvironmentObject var appState: AppState

    @State private var displayPercent: Int = 0
    @State private var stepIndex = 0

    private let steps = [
        "onboarding_processing_step1",
        "onboarding_processing_step2",
        "onboarding_processing_step3"
    ]

    /// Non-linear keyframes: (targetPercent, durationToReach)
    /// Slow start → medium middle → fast finish
    private let keyframes: [(percent: Int, duration: Double)] = [
        (15, 0.8),    // 0→15%  in 0.8s  — slow start, "receiving data"
        (35, 1.0),    // 15→35% in 1.0s  — still analyzing
        (58, 0.9),    // 35→58% in 0.9s  — step 2 kicks in
        (78, 0.7),    // 58→78% in 0.7s  — building plan
        (92, 0.5),    // 78→92% in 0.5s  — accelerating
        (100, 0.3)    // 92→100% in 0.3s — snap to done
    ]

    private var struggles: [String] {
        appState.userProfile.struggles.prefix(5).compactMap {
            ProblemType(rawValue: $0)?.displayName
        }
    }

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            // Big percentage number
            Text("\(displayPercent)%")
                .font(.system(size: 44, weight: .bold, design: .rounded))
                .foregroundStyle(AppTheme.Colors.label)
                .monospacedDigit()

            // Title
            Text(String(localized: "onboarding_processing_title"))
                .font(.system(size: 28, weight: .bold))
                .foregroundStyle(AppTheme.Colors.label)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            // Horizontal progress bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(AppTheme.Colors.accent.opacity(0.15))
                        .frame(height: 8)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(AppTheme.Colors.accent)
                        .frame(width: geo.size.width * CGFloat(displayPercent) / 100.0, height: 8)
                        .animation(.easeOut(duration: 0.15), value: displayPercent)
                }
            }
            .frame(height: 8)
            .padding(.horizontal, 40)

            // Step text
            Text(String(localized: String.LocalizationValue(steps[stepIndex])))
                .font(.system(size: 16))
                .foregroundStyle(.secondary)
                .animation(.easeInOut(duration: 0.3), value: stepIndex)

            // Struggles card
            if !struggles.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text(String(localized: "onboarding_processing_struggles_header"))
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(AppTheme.Colors.label)

                    ForEach(struggles, id: \.self) { name in
                        HStack(spacing: 8) {
                            Circle()
                                .fill(AppTheme.Colors.accent)
                                .frame(width: 6, height: 6)
                            Text(name)
                                .font(.system(size: 14))
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(AppTheme.Colors.buttonUnselected)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .padding(.horizontal, 32)
            }

            Spacer()
        }
        .background(AppBackground())
        .onAppear { startAnimation() }
    }

    // MARK: - Stepped animation

    /// Drives the percent counter through keyframes using chained DispatchQueue delays.
    /// Each keyframe interpolates 1% at a time within its duration for smooth counting.
    private func startAnimation() {
        var cumulativeDelay: Double = 0
        var previousPercent = 0

        for keyframe in keyframes {
            let startPercent = previousPercent
            let endPercent = keyframe.percent
            let steps = endPercent - startPercent
            guard steps > 0 else { continue }
            let interval = keyframe.duration / Double(steps)

            for i in 0..<steps {
                let targetPercent = startPercent + i + 1
                let delay = cumulativeDelay + interval * Double(i)

                DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
                    displayPercent = targetPercent

                    // Switch step text at 35% and 78%
                    if targetPercent == 35 { stepIndex = 1 }
                    if targetPercent == 78 { stepIndex = 2 }
                }
            }

            cumulativeDelay += keyframe.duration
            previousPercent = endPercent
        }

        // Total animation = sum of keyframe durations (~4.2s) + small buffer
        DispatchQueue.main.asyncAfter(deadline: .now() + cumulativeDelay + 0.5) {
            next()
        }
    }
}
