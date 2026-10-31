import AVFoundation
import UIKit
import UserNotifications
import WebKit

final class ViewController: UIViewController {
    private let stack = UIStackView()
    private let statusLabel = UILabel()
    private let cameraLabel = UILabel()
    private let microphoneLabel = UILabel()
    private let notificationLabel = UILabel()
    private let deepLinkLabel = UILabel()
    private let fileLabel = UILabel()
    private let backgroundLabel = UILabel()
    private let webView = WKWebView()

    private let fileURL = FileManager.default.urls(
        for: .documentDirectory,
        in: .userDomainMask
    )[0].appendingPathComponent("qa-week19.txt")

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        configureLayout()
        configureObservers()
        configureWebView()
        refreshInitialState()
    }

    private func configureLayout() {
        let scrollView = UIScrollView()
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(scrollView)

        stack.axis = .vertical
        stack.spacing = 12
        stack.alignment = .fill
        stack.translatesAutoresizingMaskIntoConstraints = false
        scrollView.addSubview(stack)

        NSLayoutConstraint.activate([
            scrollView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            scrollView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            scrollView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            stack.topAnchor.constraint(equalTo: scrollView.contentLayoutGuide.topAnchor, constant: 20),
            stack.leadingAnchor.constraint(equalTo: scrollView.contentLayoutGuide.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: scrollView.contentLayoutGuide.trailingAnchor, constant: -20),
            stack.bottomAnchor.constraint(equalTo: scrollView.contentLayoutGuide.bottomAnchor, constant: -20),
            stack.widthAnchor.constraint(equalTo: scrollView.frameLayoutGuide.widthAnchor, constant: -40),
        ])

        addLabel("QA iOS Fixture", identifier: "fixture-title", style: .title1)
        addLabel("ready", identifier: "fixture-status")
        addButton("Request Camera Permission", identifier: "request-camera") {
            self.requestCamera()
        }
        addLabel("camera: unknown", identifier: "camera-status", into: cameraLabel)
        addButton("Request Microphone Permission", identifier: "request-microphone") {
            self.requestMicrophone()
        }
        addLabel("microphone: unknown", identifier: "microphone-status", into: microphoneLabel)
        addButton("Request Notification Permission", identifier: "request-notifications") {
            self.requestNotificationPermission()
        }
        addButton("Send Local Notification", identifier: "send-notification") {
            self.sendLocalNotification()
        }
        addLabel("notifications: unknown", identifier: "notification-status", into: notificationLabel)
        addButton("Simulate Deep Link", identifier: "simulate-deep-link") {
            self.handleDeepLink(
                URL(string: "qaweek19://system-interactions?case=deep-link")!
            )
        }
        addLabel("deep link: idle", identifier: "deep-link-status", into: deepLinkLabel)
        addButton("Write Fixture File", identifier: "write-file") {
            self.writeFixtureFile()
        }
        addButton("Read Fixture File", identifier: "read-file") {
            self.readFixtureFile()
        }
        addLabel("file: idle", identifier: "file-status", into: fileLabel)
        addLabel("background: idle", identifier: "background-status", into: backgroundLabel)
        addLabel("WebView", identifier: "webview-title", style: .headline)
        webView.accessibilityIdentifier = "fixture-webview"
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.heightAnchor.constraint(equalToConstant: 260).isActive = true
        stack.addArrangedSubview(webView)
    }

    private func addLabel(
        _ text: String,
        identifier: String,
        style: UIFont.TextStyle = .body,
        into target: UILabel? = nil
    ) {
        let label = target ?? UILabel()
        label.text = text
        label.font = UIFont.preferredFont(forTextStyle: style)
        label.numberOfLines = 0
        label.accessibilityIdentifier = identifier
        stack.addArrangedSubview(label)
    }

    private func addButton(
        _ title: String,
        identifier: String,
        action: @escaping () -> Void
    ) {
        let button = UIButton(type: .system)
        button.setTitle(title, for: .normal)
        button.accessibilityIdentifier = identifier
        button.contentHorizontalAlignment = .leading
        button.addAction(UIAction { _ in action() }, for: .touchUpInside)
        stack.addArrangedSubview(button)
    }

    private func configureObservers() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleDeepLinkNotification(_:)),
            name: .fixtureDeepLink,
            object: nil
        )
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(appDidEnterBackground),
            name: UIApplication.didEnterBackgroundNotification,
            object: nil
        )
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(appWillEnterForeground),
            name: UIApplication.willEnterForegroundNotification,
            object: nil
        )
    }

    private func configureWebView() {
        let html = """
        <!doctype html>
        <html>
          <body>
            <h2 id="web-title">QA WebView</h2>
            <div id="web-status">ready</div>
            <button id="web-accept">Web Accept</button>
          </body>
        </html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    private func refreshInitialState() {
        cameraLabel.text = "camera: \(cameraAuthorizationText())"
        microphoneLabel.text = "microphone: \(microphoneAuthorizationText())"
        backgroundLabel.text = "background: launches=\(UserDefaults.standard.integer(forKey: "fixture.resumeCount"))"
    }

    private func requestCamera() {
        AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
            DispatchQueue.main.async {
                self?.cameraLabel.text = "camera: \(granted ? "granted" : "denied")"
            }
        }
    }

    private func requestMicrophone() {
        AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
            DispatchQueue.main.async {
                self?.microphoneLabel.text = "microphone: \(granted ? "granted" : "denied")"
            }
        }
    }

    private func cameraAuthorizationText() -> String {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: return "granted"
        case .denied: return "denied"
        case .restricted: return "restricted"
        case .notDetermined: return "not-determined"
        @unknown default: return "unknown"
        }
    }

    private func microphoneAuthorizationText() -> String {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: return "granted"
        case .denied: return "denied"
        case .restricted: return "restricted"
        case .notDetermined: return "not-determined"
        @unknown default: return "unknown"
        }
    }

    private func requestNotificationPermission() {
        UNUserNotificationCenter.current().requestAuthorization(
            options: [.alert, .sound, .badge]
        ) { [weak self] granted, error in
            DispatchQueue.main.async {
                if let error {
                    self?.notificationLabel.text = "notifications: error \(error.localizedDescription)"
                } else {
                    self?.notificationLabel.text = "notifications: \(granted ? "authorized" : "denied")"
                }
            }
        }
    }

    private func sendLocalNotification() {
        let content = UNMutableNotificationContent()
        content.title = "QA Week19"
        content.body = "Fixture local notification"
        content.sound = .default
        let request = UNNotificationRequest(
            identifier: "qa-week19-local",
            content: content,
            trigger: UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
        )
        UNUserNotificationCenter.current().add(request) { [weak self] error in
            DispatchQueue.main.async {
                self?.notificationLabel.text = error == nil
                    ? "notifications: scheduled"
                    : "notifications: error \(error!.localizedDescription)"
            }
        }
    }

    @objc private func handleDeepLinkNotification(_ notification: Notification) {
        guard let url = notification.object as? URL else {
            return
        }
        DispatchQueue.main.async {
            self.handleDeepLink(url)
        }
    }

    private func handleDeepLink(_ url: URL) {
        deepLinkLabel.text = "deep link: opened \(url.absoluteString)"
    }

    private func writeFixtureFile() {
        do {
            try "week19-file".write(to: fileURL, atomically: true, encoding: .utf8)
            fileLabel.text = "file: written"
        } catch {
            fileLabel.text = "file: error \(error.localizedDescription)"
        }
    }

    private func readFixtureFile() {
        do {
            let value = try String(contentsOf: fileURL, encoding: .utf8)
            fileLabel.text = "file: read \(value)"
        } catch {
            fileLabel.text = "file: error \(error.localizedDescription)"
        }
    }

    @objc private func appDidEnterBackground() {
        let count = UserDefaults.standard.integer(forKey: "fixture.backgroundCount") + 1
        UserDefaults.standard.set(count, forKey: "fixture.backgroundCount")
    }

    @objc private func appWillEnterForeground() {
        let count = UserDefaults.standard.integer(forKey: "fixture.backgroundCount")
        backgroundLabel.text = "background: resumed \(count)"
    }
}
