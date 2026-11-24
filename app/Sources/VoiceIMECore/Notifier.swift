import Foundation
import UserNotifications
import os

/// ユーザー向け通知の抽象インターフェース。
@MainActor
public protocol UserNotifying: AnyObject {
    func requestAuthorizationIfAvailable()
    func notify(title: String, body: String)
}

/// `UNUserNotificationCenter` でバナー通知を出す通知器。`.app` バンドル外実行時はログ出力へ安全にフォールバックする。
@MainActor
public final class SystemUserNotifier: NSObject, UserNotifying {
    private nonisolated static let logger = Logger(subsystem: "com.voiceime.app", category: "Notifier")
    private let delegateProxy = NotificationDelegateProxy()
    private let isAppBundle: Bool

    public override init() {
        let bundle = Bundle.main
        self.isAppBundle = (bundle.bundleURL.pathExtension == "app" && bundle.bundleIdentifier != nil)
        super.init()
        if isAppBundle {
            UNUserNotificationCenter.current().delegate = delegateProxy
        }
    }

    public func requestAuthorizationIfAvailable() {
        guard isAppBundle else { return }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, error in
            if let error {
                Self.logger.warning("通知権限の要求に失敗しました: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    public func notify(title: String, body: String) {
        Self.logger.notice("[\(title, privacy: .public)] \(body, privacy: .public)")
        guard isAppBundle else {
            fputs("[VoiceIME] \(title): \(body)\n", stderr)
            return
        }

        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )
        UNUserNotificationCenter.current().add(request) { error in
            if let error {
                Self.logger.warning("通知の配信に失敗しました: \(error.localizedDescription, privacy: .public)")
            }
        }
    }
}

/// アプリ前面時にも通知バナーを表示するための `UNUserNotificationCenterDelegate` 実装。
private final class NotificationDelegateProxy: NSObject, UNUserNotificationCenterDelegate, @unchecked Sendable {
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list])
    }
}
