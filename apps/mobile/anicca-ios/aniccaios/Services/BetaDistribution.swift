import Foundation
import os

/// Beta分布からのサンプリングを提供する
/// Thompson Samplingで使用
struct BetaDistribution {
    let alpha: Double
    let beta: Double
    
    private let logger = Logger(subsystem: "com.anicca.ios", category: "BetaDistribution")
    
    init(alpha: Double, beta: Double) {
        // 最小値は1.0（事前分布の無情報事前分布）
        self.alpha = max(1.0, alpha)
        self.beta = max(1.0, beta)
    }
    
    /// Beta分布からサンプルを取得
    /// Gamma分布を使用した正確なサンプリング（Marsaglia and Tsang's method）
    func sample() -> Double {
        let x = gammaSample(shape: alpha)
        let y = gammaSample(shape: beta)
        
        // x / (x + y) がBeta(alpha, beta)からのサンプル
        let result = x / (x + y)
        
        // NaNや無限大を防ぐ
        if result.isNaN || result.isInfinite {
            logger.warning("Invalid sample generated, returning mean estimate")
            return alpha / (alpha + beta)
        }
        
        return result
    }
    
    /// 期待値（平均）を返す
    var mean: Double {
        return alpha / (alpha + beta)
    }
    
    /// 分散を返す
    var variance: Double {
        let sum = alpha + beta
        return (alpha * beta) / (sum * sum * (sum + 1))
    }
    
    /// Gamma分布からのサンプリング（Marsaglia and Tsang's method）
    private func gammaSample(shape: Double) -> Double {
        if shape < 1.0 {
            // shape < 1の場合、変換を使用
            let u = Double.random(in: 0..<1)
            return gammaSample(shape: shape + 1.0) * pow(u, 1.0 / shape)
        }
        
        let d = shape - 1.0 / 3.0
        let c = 1.0 / sqrt(9.0 * d)
        
        while true {
            var x: Double
            var v: Double
            
            repeat {
                x = normalSample()
                v = 1.0 + c * x
            } while v <= 0
            
            v = v * v * v
            let u = Double.random(in: 0..<1)
            
            if u < 1.0 - 0.0331 * (x * x) * (x * x) {
                return d * v
            }
            
            if log(u) < 0.5 * x * x + d * (1.0 - v + log(v)) {
                return d * v
            }
        }
    }
    
    /// 標準正規分布からのサンプリング（Box-Muller変換）
    private func normalSample() -> Double {
        let u1 = Double.random(in: 0..<1)
        let u2 = Double.random(in: 0..<1)
        return sqrt(-2.0 * log(u1)) * cos(2.0 * .pi * u2)
    }
}


