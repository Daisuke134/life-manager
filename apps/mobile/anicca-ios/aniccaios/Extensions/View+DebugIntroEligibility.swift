import SwiftUI
import RevenueCat
@_spi(Internal) import RevenueCatUI

extension View {
    /// DEBUG ビルドでは常にイントロオファー eligible として表示する
    @ViewBuilder
    func applyDebugIntroEligibility() -> some View {
        #if DEBUG
        self.environmentObject(
            TrialOrIntroEligibilityChecker { packages in
                Dictionary(uniqueKeysWithValues: packages.map { ($0, IntroEligibilityStatus.eligible) })
            }
        )
        #else
        self
        #endif
    }
}
