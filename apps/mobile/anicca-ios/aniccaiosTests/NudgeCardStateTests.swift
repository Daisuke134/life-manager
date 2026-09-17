import XCTest
@testable import aniccaios

/// NudgeCard状態管理のテスト
@MainActor
final class NudgeCardStateTests: XCTestCase {

    override func tearDown() async throws {
        // Cleanup: ensure no lingering state
        AppState.shared.dismissNudgeCard()
    }

    /// showNudgeCardが状態を即座に設定することを確認
    func test_showNudgeCard_setsState() async throws {
        // Given
        let appState = AppState.shared
        let testContent = NudgeContent.contentForToday(for: .stayingUpLate)

        // Precondition
        XCTAssertNil(appState.pendingNudgeCard, "Should start with no pending card")

        // When
        appState.showNudgeCard(testContent)

        // Then
        XCTAssertNotNil(appState.pendingNudgeCard, "pendingNudgeCard should be set immediately")
        XCTAssertEqual(appState.pendingNudgeCard?.problemType, .stayingUpLate)
    }

    /// dismissNudgeCardが状態をクリアすることを確認
    func test_dismissNudgeCard_clearsState() async throws {
        // Given
        let appState = AppState.shared
        let testContent = NudgeContent.contentForToday(for: .stayingUpLate)
        appState.showNudgeCard(testContent)

        // Precondition
        XCTAssertNotNil(appState.pendingNudgeCard)

        // When
        appState.dismissNudgeCard()

        // Then
        XCTAssertNil(appState.pendingNudgeCard, "pendingNudgeCard should be cleared")
    }

    /// 複数回showNudgeCardを呼んでも最後のものが有効
    func test_showNudgeCard_replacesExisting() async throws {
        // Given
        let appState = AppState.shared
        let content1 = NudgeContent.contentForToday(for: .stayingUpLate)
        let content2 = NudgeContent.contentForToday(for: .cantWakeUp)

        // When
        appState.showNudgeCard(content1)
        appState.showNudgeCard(content2)

        // Then
        XCTAssertEqual(appState.pendingNudgeCard?.problemType, .cantWakeUp)
    }
}
