import XCTest
@testable import aniccaios

final class BetaDistributionTests: XCTestCase {
    
    // MARK: - sample() のテスト
    
    /// sample() は 0〜1 の範囲の値を返すこと
    func test_sample_returns_value_between_0_and_1() {
        let distribution = BetaDistribution(alpha: 1.0, beta: 1.0)
        
        for _ in 0..<1000 {
            let sample = distribution.sample()
            XCTAssertGreaterThanOrEqual(sample, 0.0)
            XCTAssertLessThanOrEqual(sample, 1.0)
        }
    }
    
    /// alpha が高いと sample の平均値が高くなること
    func test_sample_higher_alpha_produces_higher_mean() {
        let lowAlpha = BetaDistribution(alpha: 1.0, beta: 10.0)
        let highAlpha = BetaDistribution(alpha: 10.0, beta: 1.0)
        
        let lowSamples = (0..<1000).map { _ in lowAlpha.sample() }
        let highSamples = (0..<1000).map { _ in highAlpha.sample() }
        
        let lowMean = lowSamples.reduce(0, +) / Double(lowSamples.count)
        let highMean = highSamples.reduce(0, +) / Double(highSamples.count)
        
        XCTAssertLessThan(lowMean, 0.2, "Low alpha mean should be < 0.2")
        XCTAssertGreaterThan(highMean, 0.8, "High alpha mean should be > 0.8")
    }
    
    /// alpha=1, beta=1 は一様分布（平均 0.5 付近）
    func test_sample_uniform_distribution_has_mean_around_05() {
        let distribution = BetaDistribution(alpha: 1.0, beta: 1.0)
        
        let samples = (0..<10000).map { _ in distribution.sample() }
        let mean = samples.reduce(0, +) / Double(samples.count)
        
        XCTAssertGreaterThan(mean, 0.45)
        XCTAssertLessThan(mean, 0.55)
    }
}

