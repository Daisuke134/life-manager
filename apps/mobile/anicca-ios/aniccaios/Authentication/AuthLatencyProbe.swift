import Foundation
import OSLog

struct AuthLatencyProbe {
    private let logger = Logger(subsystem: "com.anicca.ios", category: "AuthLatency")
    private var start: Date?
    
    mutating func mark(_ label: StaticString) {
        let now = Date()
        if let start {
            let elapsed = now.timeIntervalSince(start)
            logger.log("\(label) latency=\(String(format: "%.3f", elapsed))s")
        }
        start = now
    }
    
    func finish(_ label: StaticString, extra: String = "") {
        guard let start else { return }
        let elapsed = Date().timeIntervalSince(start)
        logger.log("\(label) total=\(String(format: "%.3f", elapsed))s \(extra, privacy: .public)")
    }
}

