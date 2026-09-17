import XCTest
@testable import aniccaios

final class PushTokenServiceTests: XCTestCase {
    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [TestURLProtocol.self]
        NetworkSessionManager.testSession = URLSession(configuration: config)
        UserDefaults.standard.set(false, forKey: "com.anicca.apnsTokenRegistered")
    }

    override func tearDown() {
        NetworkSessionManager.testSession = nil
        TestURLProtocol.requestHandler = nil
        super.tearDown()
    }

    func testRegister_sendsHexTokenWithHeaders() async {
        // 32 bytes -> 64 hex chars
        let tokenBytes = Data((0..<32).map { UInt8($0) })
        let expectedHex = tokenBytes.map { String(format: "%02x", $0) }.joined()

        let exp = expectation(description: "request captured")

        TestURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertTrue(request.url?.absoluteString.contains("/mobile/push/token") == true)
            XCTAssertEqual(request.value(forHTTPHeaderField: "device-id"), AppState.shared.resolveDeviceId())
            XCTAssertNotNil(request.value(forHTTPHeaderField: "x-timezone"))
            XCTAssertNotNil(request.value(forHTTPHeaderField: "x-lang"))

            let body = request.httpBody ?? Data()
            let obj = try JSONSerialization.jsonObject(with: body) as? [String: Any]
            XCTAssertEqual(obj?["token"] as? String, expectedHex)
            XCTAssertEqual(obj?["platform"] as? String, "ios")

            exp.fulfill()
            let resp = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (resp, Data("{\"ok\":true,\"remoteDeliveryEnabled\":true,\"remoteProblemNudgesEnabled\":true}".utf8))
        }

        await PushTokenService.shared.register(deviceToken: tokenBytes)
        await fulfillment(of: [exp], timeout: 2.0)
        XCTAssertTrue(UserDefaults.standard.bool(forKey: "com.anicca.apnsTokenRegistered"))
    }

    func testRegister_remoteDisabled_marksUnregistered() async {
        UserDefaults.standard.set(true, forKey: "com.anicca.apnsTokenRegistered")
        let tokenBytes = Data((0..<32).map { UInt8($0) })

        let exp = expectation(description: "request captured")
        TestURLProtocol.requestHandler = { request in
            exp.fulfill()
            let resp = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (resp, Data("{\"ok\":true,\"remoteDeliveryEnabled\":false,\"remoteProblemNudgesEnabled\":false}".utf8))
        }

        await PushTokenService.shared.register(deviceToken: tokenBytes)
        await fulfillment(of: [exp], timeout: 2.0)
        XCTAssertFalse(UserDefaults.standard.bool(forKey: "com.anicca.apnsTokenRegistered"))
    }
}
