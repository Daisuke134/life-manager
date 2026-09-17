import SwiftUI
import UIKit

/// Vertical full-screen paging via UIPageViewController.
/// Used by FeedRootView to swipe through quote cards top-to-bottom (1:1 i.am app pattern).
struct VerticalPager<Page: View>: UIViewControllerRepresentable {
    let count: Int
    @Binding var currentIndex: Int
    let pageContent: (Int) -> Page

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIViewController(context: Context) -> UIPageViewController {
        let pvc = UIPageViewController(
            transitionStyle: .scroll,
            navigationOrientation: .vertical,
            options: nil
        )
        pvc.dataSource = context.coordinator
        pvc.delegate = context.coordinator
        pvc.view.backgroundColor = UIColor.clear

        for view in pvc.view.subviews {
            if let scroll = view as? UIScrollView {
                scroll.backgroundColor = UIColor.clear
            }
        }

        if count > 0 {
            let first = context.coordinator.hosting(for: clampedIndex(currentIndex))
            pvc.setViewControllers([first], direction: .forward, animated: false)
        }
        return pvc
    }

    func updateUIViewController(_ pvc: UIPageViewController, context: Context) {
        context.coordinator.parent = self
        guard count > 0 else { return }

        let target = clampedIndex(currentIndex)
        let currentHost = pvc.viewControllers?.first as? IndexedHosting
        if currentHost?.index != target {
            let direction: UIPageViewController.NavigationDirection =
                (currentHost?.index ?? 0) < target ? .forward : .reverse
            let next = context.coordinator.hosting(for: target)
            pvc.setViewControllers([next], direction: direction, animated: true)
        }
    }

    private func clampedIndex(_ i: Int) -> Int {
        min(max(0, i), max(0, count - 1))
    }

    final class Coordinator: NSObject, UIPageViewControllerDataSource, UIPageViewControllerDelegate {
        var parent: VerticalPager

        init(_ parent: VerticalPager) { self.parent = parent }

        func hosting(for index: Int) -> IndexedHosting {
            let host = IndexedHosting(index: index, rootView: AnyView(parent.pageContent(index)))
            host.view.backgroundColor = UIColor.clear
            if #available(iOS 16.0, *) {
                host.sizingOptions = []
            }
            host.view.translatesAutoresizingMaskIntoConstraints = true
            host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
            return host
        }

        func pageViewController(_ pvc: UIPageViewController,
                                viewControllerBefore vc: UIViewController) -> UIViewController? {
            guard let host = vc as? IndexedHosting, host.index > 0 else { return nil }
            return hosting(for: host.index - 1)
        }

        func pageViewController(_ pvc: UIPageViewController,
                                viewControllerAfter vc: UIViewController) -> UIViewController? {
            guard let host = vc as? IndexedHosting,
                  host.index + 1 < parent.count else { return nil }
            return hosting(for: host.index + 1)
        }

        func pageViewController(_ pvc: UIPageViewController,
                                didFinishAnimating finished: Bool,
                                previousViewControllers: [UIViewController],
                                transitionCompleted completed: Bool) {
            guard completed,
                  let host = pvc.viewControllers?.first as? IndexedHosting else { return }
            if parent.currentIndex != host.index {
                parent.currentIndex = host.index
            }
        }
    }
}

final class IndexedHosting: UIHostingController<AnyView> {
    let index: Int
    init(index: Int, rootView: AnyView) {
        self.index = index
        super.init(rootView: rootView)
    }
    @MainActor required dynamic init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}
