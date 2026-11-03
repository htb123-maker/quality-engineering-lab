import UIKit
import UserNotifications

extension Notification.Name {
    static let fixtureDeepLink = Notification.Name("FixtureDeepLink")
    static let fixtureNotificationOpened = Notification.Name("FixtureNotificationOpened")
}

final class FixtureNotificationDelegate: NSObject, UNUserNotificationCenterDelegate {
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        UserDefaults.standard.set(true, forKey: "fixture.notificationOpened")
        NotificationCenter.default.post(name: .fixtureNotificationOpened, object: nil)
        completionHandler()
    }
}

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    private let notificationDelegate = FixtureNotificationDelegate()
    private var pendingDeepLink: URL?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        let viewController = ViewController()
        window.rootViewController = viewController
        window.makeKeyAndVisible()
        self.window = window
        UNUserNotificationCenter.current().delegate = notificationDelegate
        if let pendingDeepLink {
            viewController.handleDeepLink(pendingDeepLink)
            self.pendingDeepLink = nil
        }
        return true
    }

    func application(
        _ app: UIApplication,
        open url: URL,
        options: [UIApplication.OpenURLOptionsKey: Any] = [:]
    ) -> Bool {
        if let viewController = window?.rootViewController as? ViewController {
            viewController.handleDeepLink(url)
        } else {
            pendingDeepLink = url
        }
        return true
    }
}
