import RevenueCat

extension Offering {
    var hasPurchasablePackages: Bool {
        !availablePackages.isEmpty
    }

    /// 表示しても安全かどうかの厳密な判定
    /// RevenueCatUIのCarouselViewが0除算エラーを起こさないように、商品IDまで確認
    var isSafeToDisplay: Bool {
        // 1. パッケージ自体が空ならNG
        guard !availablePackages.isEmpty else {
            print("[Offering] Empty packages: identifier=\(identifier)")
            return false
        }
        
        // 2. 全てのパッケージが有効な商品IDを持っているか確認
        // (空文字だとRevenueCatUI内部で予期せぬ挙動になる可能性があります)
        let allValid = availablePackages.allSatisfy { !$0.storeProduct.productIdentifier.isEmpty }
        if !allValid {
            print("[Offering] Invalid product IDs found: identifier=\(identifier)")
        }
        return allValid
    }

    var containsEmptyCarousel: Bool {
        // isSafeToDisplayがfalseなら、Carouselは空または不正とみなす
        return !isSafeToDisplay
    }
}

