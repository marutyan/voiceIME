import CoreGraphics
import Foundation

/// 画面下中央ピル（案A）の寸法・アニメーション時間・文言の単一情報源。
/// 値は UI 試作 `docs/ui-mock/overlay.html`（`.pill-a`、1 CSS px = 1 macOS pt）に揃える。
public enum OverlayMetrics {
    public static let cornerRadius: CGFloat = 16
    public static let borderWidth: CGFloat = 1
    public static let topHighlightHeight: CGFloat = 0.5

    public static let compactRecordingSize = CGSize(width: 124, height: 32)
    public static let partialRecordingWidth: CGFloat = 300
    public static let partialRecordingMinHeight: CGFloat = 60
    public static let processingSize = CGSize(width: 112, height: 32)
    public static let doneSize = CGSize(width: 32, height: 32)
    public static let errorHeight: CGFloat = 32
    public static let errorMaxWidth: CGFloat = 248

    public static let compactHorizontalPadding: CGFloat = 12
    public static let partialHorizontalPadding: CGFloat = 14
    public static let partialVerticalPadding: CGFloat = 8
    public static let rowGap: CGFloat = 8
    public static let errorRowGap: CGFloat = 6
    public static let partialSectionGap: CGFloat = 5
    public static let partialDividerBottomPadding: CGFloat = 5
    public static let dividerHeight: CGFloat = 1

    public static let recDotSize: CGFloat = 8
    /// 録音ドットの脈動リングがドット外周から広がる余白（CSS `inset: -3px`）。
    public static let recPulseInset: CGFloat = 3
    public static let recPulseLineWidth: CGFloat = 1.5

    public static let waveBarCount: Int = 9
    public static let waveBarWidth: CGFloat = 2
    public static let waveBarGap: CGFloat = 3
    public static let waveBarContainerHeight: CGFloat = 16
    public static let waveBarMinHeight: CGFloat = 4
    public static let waveBarMaxHeight: CGFloat = 16
    /// 案Aの波形バー9本の中央強調プロファイル（試作 `waveProfiles.a.weights`）。
    public static let waveBarWeights: [Double] = [0.42, 0.65, 0.85, 0.96, 1.0, 0.94, 0.82, 0.62, 0.40]

    public static let timerFontSize: CGFloat = 12
    public static let timerMinWidth: CGFloat = 30
    public static let partialFontSize: CGFloat = 12
    /// 途中結果テキストの行高（CSS `font-size: 12px; line-height: 1.4`）。
    public static let partialLineHeight: CGFloat = 16.8
    public static let partialMaxLines: Int = 2
    public static let statusFontSize: CGFloat = 12

    public static let spinnerSize: CGFloat = 14
    public static let spinnerLineWidth: CGFloat = 2
    public static let checkIconSize: CGFloat = 16
    public static let checkStrokeWidth: CGFloat = 2.4
    public static let errorIconSize: CGFloat = 14

    /// Dock 上端からピル下端までの距離（試作 `bottom: 66px` − Dock `8 + 44 = 52px`）。
    public static let bottomMarginAboveDock: CGFloat = 14

    /// 完了チェックを表示してから自動フェードアウトを始めるまでの待ち時間（約0.9秒、試作 `880ms`）。
    public static let doneAutoHideDelay: Duration = .milliseconds(880)
    /// エラーピルを自動消去するまでの表示時間。
    public static let errorAutoHideDelay: Duration = .seconds(3)

    public static let stateTransitionDuration: TimeInterval = 0.18
    public static let showHideAnimationDuration: TimeInterval = 0.22
    public static let doneFadeOutDuration: TimeInterval = 0.28
    public static let checkDrawDuration: TimeInterval = 0.24
    public static let partialChunkFadeDuration: TimeInterval = 0.22
    public static let recPulseDuration: TimeInterval = 1.5
    public static let spinnerRotationDuration: TimeInterval = 0.72

    public static let processingText = "整形中…"

    /// メニューバーのオン／オフ項目に表示するタイトルを返す。
    public static func menuTitle(isEnabled: Bool) -> String {
        isEnabled ? "録音中の表示（オン）" : "録音中の表示（オフ）"
    }
}

/// UI 非依存で色値を保持・検証するための sRGB RGBA 構造体。
public struct OverlayRGBAColor: Sendable, Equatable {
    public let red: CGFloat
    public let green: CGFloat
    public let blue: CGFloat
    public let alpha: CGFloat

    public init(r255: CGFloat, g255: CGFloat, b255: CGFloat, alpha: CGFloat = 1.0) {
        self.red = r255 / 255.0
        self.green = g255 / 255.0
        self.blue = b255 / 255.0
        self.alpha = alpha
    }
}

/// CSS `box-shadow` 1段分に対応する影の幾何・不透明度仕様。
public struct OverlayShadowSpec: Sendable, Equatable {
    public let offsetY: CGFloat
    public let blurRadius: CGFloat
    public let alpha: CGFloat

    public init(offsetY: CGFloat, blurRadius: CGFloat, alpha: CGFloat) {
        self.offsetY = offsetY
        self.blurRadius = blurRadius
        self.alpha = alpha
    }
}

/// 試作 `docs/ui-mock/overlay.html` のライト／ダーク両モードの配色定義。
public struct OverlayThemePalette: Sendable, Equatable {
    public let hudBackground: OverlayRGBAColor
    public let hudBorder: OverlayRGBAColor
    public let hudHighlight: OverlayRGBAColor
    public let hudText: OverlayRGBAColor
    public let hudTextMuted: OverlayRGBAColor
    public let hudDivider: OverlayRGBAColor
    public let sysRed: OverlayRGBAColor
    public let sysRedText: OverlayRGBAColor
    public let sysRedTint: OverlayRGBAColor
    public let sysRedBorder: OverlayRGBAColor
    public let sysGreen: OverlayRGBAColor
    public let sysGreenTint: OverlayRGBAColor
    public let doneBorder: OverlayRGBAColor
    public let spinnerTrack: OverlayRGBAColor
    public let spinnerHead: OverlayRGBAColor
    public let primaryShadow: OverlayShadowSpec
    public let secondaryShadow: OverlayShadowSpec

    /// ライトモード配色（試作 `:root` の値そのまま）。
    public static let light = OverlayThemePalette(
        hudBackground: OverlayRGBAColor(r255: 250, g255: 250, b255: 252, alpha: 0.86),
        hudBorder: OverlayRGBAColor(r255: 0, g255: 0, b255: 0, alpha: 0.10),
        hudHighlight: OverlayRGBAColor(r255: 255, g255: 255, b255: 255, alpha: 0.90),
        hudText: OverlayRGBAColor(r255: 29, g255: 29, b255: 31, alpha: 0.92),
        hudTextMuted: OverlayRGBAColor(r255: 29, g255: 29, b255: 31, alpha: 0.56),
        hudDivider: OverlayRGBAColor(r255: 0, g255: 0, b255: 0, alpha: 0.10),
        sysRed: OverlayRGBAColor(r255: 255, g255: 59, b255: 48, alpha: 1.0),
        sysRedText: OverlayRGBAColor(r255: 200, g255: 30, b255: 23, alpha: 1.0),
        sysRedTint: OverlayRGBAColor(r255: 255, g255: 59, b255: 48, alpha: 0.10),
        sysRedBorder: OverlayRGBAColor(r255: 255, g255: 59, b255: 48, alpha: 0.34),
        sysGreen: OverlayRGBAColor(r255: 40, g255: 205, b255: 65, alpha: 1.0),
        sysGreenTint: OverlayRGBAColor(r255: 40, g255: 205, b255: 65, alpha: 0.12),
        doneBorder: OverlayRGBAColor(r255: 40, g255: 205, b255: 65, alpha: 0.40),
        spinnerTrack: OverlayRGBAColor(r255: 0, g255: 0, b255: 0, alpha: 0.14),
        spinnerHead: OverlayRGBAColor(r255: 29, g255: 29, b255: 31, alpha: 0.80),
        primaryShadow: OverlayShadowSpec(offsetY: 8, blurRadius: 24, alpha: 0.13),
        secondaryShadow: OverlayShadowSpec(offsetY: 1, blurRadius: 3, alpha: 0.09)
    )

    /// ダークモード配色（試作 `html[data-theme="dark"]` の値そのまま）。
    public static let dark = OverlayThemePalette(
        hudBackground: OverlayRGBAColor(r255: 38, g255: 38, b255: 43, alpha: 0.86),
        hudBorder: OverlayRGBAColor(r255: 255, g255: 255, b255: 255, alpha: 0.15),
        hudHighlight: OverlayRGBAColor(r255: 255, g255: 255, b255: 255, alpha: 0.12),
        hudText: OverlayRGBAColor(r255: 245, g255: 245, b255: 247, alpha: 0.94),
        hudTextMuted: OverlayRGBAColor(r255: 245, g255: 245, b255: 247, alpha: 0.60),
        hudDivider: OverlayRGBAColor(r255: 255, g255: 255, b255: 255, alpha: 0.14),
        sysRed: OverlayRGBAColor(r255: 255, g255: 69, b255: 58, alpha: 1.0),
        sysRedText: OverlayRGBAColor(r255: 255, g255: 105, b255: 97, alpha: 1.0),
        sysRedTint: OverlayRGBAColor(r255: 255, g255: 69, b255: 58, alpha: 0.18),
        sysRedBorder: OverlayRGBAColor(r255: 255, g255: 69, b255: 58, alpha: 0.42),
        sysGreen: OverlayRGBAColor(r255: 48, g255: 209, b255: 88, alpha: 1.0),
        sysGreenTint: OverlayRGBAColor(r255: 48, g255: 209, b255: 88, alpha: 0.16),
        doneBorder: OverlayRGBAColor(r255: 40, g255: 205, b255: 65, alpha: 0.40),
        spinnerTrack: OverlayRGBAColor(r255: 255, g255: 255, b255: 255, alpha: 0.18),
        spinnerHead: OverlayRGBAColor(r255: 245, g255: 245, b255: 247, alpha: 0.90),
        primaryShadow: OverlayShadowSpec(offsetY: 12, blurRadius: 30, alpha: 0.50),
        secondaryShadow: OverlayShadowSpec(offsetY: 1, blurRadius: 4, alpha: 0.36)
    )
}

/// 録音中オーバーレイに表示する途中結果テキストの状態。
public struct OverlayRecordingState: Sendable, Equatable {
    /// 直前までの区間で確定した途中結果（薄い色で表示）。
    public let partialPrefix: String
    /// 最後に届いた区間の途中結果（濃い色で表示し、受信時にフェードインする）。
    public let partialLatest: String
    /// `partial` が更新された回数。同一文言の更新でもアニメーションを判定するために使う。
    public let partialRevision: Int

    public init(
        partialPrefix: String = "",
        partialLatest: String = "",
        partialRevision: Int = 0
    ) {
        self.partialPrefix = partialPrefix
        self.partialLatest = partialLatest
        self.partialRevision = partialRevision
    }

    /// 途中結果が1文字以上届いており、幅300ptの展開表示にすべきか。
    public var hasPartial: Bool {
        !partialPrefix.isEmpty || !partialLatest.isEmpty
    }

    /// prefix と latest を結合した途中結果全文。
    public var fullPartialText: String {
        partialPrefix + partialLatest
    }
}

/// オーバーレイ（案Aピル）が表示する状態。
public enum OverlayState: Sendable, Equatable {
    /// 待機時または表示オフ時。ウィンドウ自体を非表示にする。
    case hidden
    /// 録音中。`hasPartial` が真のときは幅300ptへ上方向展開する。
    case recording(OverlayRecordingState)
    /// 録音終了後から結果到着までの処理中（スピナー＋「整形中…」）。
    case processing
    /// 貼り付け完了。緑チェックを表示し、約0.9秒後に自動消去する。
    case done
    /// 短いエラー理由を赤ティントで表示する。
    case error(message: String)

    /// ウィンドウを画面に出すべき状態か。
    public var isVisible: Bool {
        if case .hidden = self {
            return false
        }
        return true
    }
}

/// 完了またはエラーの自動消去タイマー種別と、古いタイマー発火を無視するための世代トークン。
public enum OverlayAutoHideSchedule: Sendable, Equatable {
    case done(token: UInt64)
    case error(token: UInt64)
}

/// `AppCoordinator` のライフサイクルから `OverlayStateMachine` へ渡す入力イベント。
public enum OverlayEvent: Sendable, Equatable {
    case setEnabled(Bool)
    case recordingStarted
    case partialReceived(seq: Int, text: String)
    case recordingCancelled
    case processingStarted
    case sessionFinishedEmpty
    case pasteSucceeded
    case pasteFallback(PasteFallbackReason)
    case errorOccurred(message: String, isEngineError: Bool = false)
    case engineReady
    case autoHideTimerFired(token: UInt64)
}

/// `OverlayStateMachine.apply(_:)` が返す遷移結果とタイマー制御指示。
public struct OverlayTransition: Sendable, Equatable {
    public let displayState: OverlayState
    public let autoHideSchedule: OverlayAutoHideSchedule?
    public let shouldCancelAutoHide: Bool

    public init(
        displayState: OverlayState,
        autoHideSchedule: OverlayAutoHideSchedule? = nil,
        shouldCancelAutoHide: Bool = false
    ) {
        self.displayState = displayState
        self.autoHideSchedule = autoHideSchedule
        self.shouldCancelAutoHide = shouldCancelAutoHide
    }
}

/// `AppCoordinator` の状態遷移をオーバーレイ表示状態へ写像する UI 非依存の純粋ステートマシン。
public struct OverlayStateMachine: Sendable, Equatable {
    /// メニューの「録音中の表示」設定値。オフでも内部の進行状態は追い、オンに戻したとき即座に反映する。
    public private(set) var isEnabled: Bool
    /// 表示設定がオンのときに出すべき本来の状態。
    public private(set) var activeState: OverlayState = .hidden

    private var partialSegments: [Int: String] = [:]
    private var partialRevision: Int = 0
    private var autoHideToken: UInt64 = 0
    private var activeErrorIsEngineError: Bool = false

    public init(isEnabled: Bool = true) {
        self.isEnabled = isEnabled
    }

    /// 現在の設定を反映した最終的な表示状態。
    public var displayState: OverlayState {
        isEnabled ? activeState : .hidden
    }

    /// イベントを適用して次の表示状態と自動消去タイマー指示を返す。
    @discardableResult
    public mutating func apply(_ event: OverlayEvent) -> OverlayTransition {
        switch event {
        case let .setEnabled(enabled):
            isEnabled = enabled
            return OverlayTransition(displayState: displayState)

        case .recordingStarted:
            partialSegments.removeAll(keepingCapacity: true)
            partialRevision = 0
            activeErrorIsEngineError = false
            activeState = .recording(OverlayRecordingState())
            autoHideToken &+= 1
            return OverlayTransition(displayState: displayState, shouldCancelAutoHide: true)

        case let .partialReceived(seq, text):
            guard case .recording = activeState else {
                return OverlayTransition(displayState: displayState)
            }
            // 改行や余分な空白で2行表示枠を消費しないよう単一スペースへ正規化する。
            let normalized = text
                .components(separatedBy: .whitespacesAndNewlines)
                .filter { !$0.isEmpty }
                .joined(separator: " ")
            guard !normalized.isEmpty else {
                return OverlayTransition(displayState: displayState)
            }
            partialSegments[seq] = normalized
            partialRevision += 1
            let recordingState = buildRecordingState()
            activeState = .recording(recordingState)
            return OverlayTransition(displayState: displayState)

        case .recordingCancelled, .sessionFinishedEmpty:
            partialSegments.removeAll(keepingCapacity: false)
            activeErrorIsEngineError = false
            activeState = .hidden
            autoHideToken &+= 1
            return OverlayTransition(displayState: displayState, shouldCancelAutoHide: true)

        case .processingStarted:
            partialSegments.removeAll(keepingCapacity: false)
            activeErrorIsEngineError = false
            activeState = .processing
            autoHideToken &+= 1
            return OverlayTransition(displayState: displayState, shouldCancelAutoHide: true)

        case .pasteSucceeded:
            partialSegments.removeAll(keepingCapacity: false)
            activeErrorIsEngineError = false
            activeState = .done
            autoHideToken &+= 1
            return OverlayTransition(
                displayState: displayState,
                autoHideSchedule: .done(token: autoHideToken),
                shouldCancelAutoHide: true
            )

        case let .pasteFallback(reason):
            partialSegments.removeAll(keepingCapacity: false)
            activeErrorIsEngineError = false
            activeState = .error(message: reason.overlayMessage)
            autoHideToken &+= 1
            return OverlayTransition(
                displayState: displayState,
                autoHideSchedule: .error(token: autoHideToken),
                shouldCancelAutoHide: true
            )

        case let .errorOccurred(message, isEngineError):
            partialSegments.removeAll(keepingCapacity: false)
            activeErrorIsEngineError = isEngineError
            let cleaned = message.trimmingCharacters(in: .whitespacesAndNewlines)
            activeState = .error(message: cleaned.isEmpty ? "エラーが発生しました" : cleaned)
            autoHideToken &+= 1
            return OverlayTransition(
                displayState: displayState,
                autoHideSchedule: .error(token: autoHideToken),
                shouldCancelAutoHide: true
            )

        case .engineReady:
            if case .error = activeState, activeErrorIsEngineError {
                activeErrorIsEngineError = false
                activeState = .hidden
                autoHideToken &+= 1
                return OverlayTransition(displayState: displayState, shouldCancelAutoHide: true)
            }
            return OverlayTransition(displayState: displayState)

        case let .autoHideTimerFired(token):
            guard token == autoHideToken else {
                return OverlayTransition(displayState: displayState)
            }
            activeErrorIsEngineError = false
            activeState = .hidden
            return OverlayTransition(displayState: displayState)
        }
    }

    private func buildRecordingState() -> OverlayRecordingState {
        let sortedSeqs = partialSegments.keys.sorted()
        guard let latestSeq = sortedSeqs.last, let latestText = partialSegments[latestSeq] else {
            return OverlayRecordingState(partialRevision: partialRevision)
        }
        let prefixPieces = sortedSeqs.dropLast().compactMap { partialSegments[$0] }
        let prefix = prefixPieces.isEmpty ? "" : prefixPieces.joined(separator: " ") + " "
        return OverlayRecordingState(
            partialPrefix: prefix,
            partialLatest: latestText,
            partialRevision: partialRevision
        )
    }
}

/// 録音中の PCM サンプルから波形バー用の音量レベル（0.0〜1.0）と9本のバー高さを算出する純粋計算ヘルパー。
public enum OverlayAudioLevel {
    /// 無音とみなす下限デシベル（RMS 約 0.00316）。
    public static let floorDecibels: Double = -50.0
    /// 最大バー高さに達する上限デシベル（RMS 約 0.316）。
    public static let ceilingDecibels: Double = -10.0

    /// Int16 PCM チャンクから対数スケールで正規化した音量レベル（0.0〜1.0）を返す。
    public static func normalizedLevel(from samples: [Int16]) -> Float {
        normalizedLevel(rms: AudioSegmenter.rms(of: samples))
    }

    /// 正規化 RMS（0.0〜1.0）を人間の聴覚に近いデシベル換算で 0.0〜1.0 へ写像する。
    public static func normalizedLevel(rms: Float) -> Float {
        guard rms > 0 else { return 0 }
        let db = 20.0 * log10(max(Double(rms), 1e-6))
        let span = ceilingDecibels - floorDecibels
        let normalized = (db - floorDecibels) / span
        return Float(max(0.0, min(1.0, normalized)))
    }

    /// 現在の音量エンベロープ（0.0〜1.0）と経過時刻から案Aの波形バー9本の高さ（4〜16pt）を算出する。
    public static func barHeights(envelope: Double, timeSeconds: Double) -> [CGFloat] {
        let clampedEnvelope = max(0.0, min(1.0, envelope))
        let heightSpan = OverlayMetrics.waveBarMaxHeight - OverlayMetrics.waveBarMinHeight
        return OverlayMetrics.waveBarWeights.enumerated().map { idx, weight in
            // 試作 `tickWaveforms` と同じ位相ずらし波紋を掛け、話し声の抑揚を自然に表現する。
            let ripple = 0.65 + 0.35 * sin(timeSeconds * 11.0 + Double(idx) * 1.15)
            let level = max(0.0, min(1.0, clampedEnvelope * weight * ripple))
            return OverlayMetrics.waveBarMinHeight + heightSpan * CGFloat(level)
        }
    }

    /// 録音経過秒を `m:ss` 形式（例 `0:04`, `1:05`）へ整形する。
    public static func formatElapsed(seconds: Int) -> String {
        let safe = max(0, seconds)
        let minutes = safe / 60
        let secs = safe % 60
        return String(format: "%d:%02d", minutes, secs)
    }
}

/// マルチディスプレイ環境での前面スクリーン選択と下中央アンカー座標計算を行う純粋レイアウト計算。
public enum OverlayPanelLayout {
    /// `NSScreen` のフレーム情報を UI 非依存で扱うための軽量構造体（AppKit 左下原点座標）。
    public struct ScreenGeometry: Sendable, Equatable {
        public let frame: CGRect
        public let visibleFrame: CGRect

        public init(frame: CGRect, visibleFrame: CGRect) {
            self.frame = frame
            self.visibleFrame = visibleFrame
        }
    }

    /// 前面アプリのウィンドウ（CoreGraphics 左上原点座標）、`NSScreen.main`、マウス位置の優先順で表示対象スクリーンを選ぶ。
    public static func selectScreenIndex(
        screens: [ScreenGeometry],
        frontmostWindowCGFrame: CGRect?,
        mainScreenIndex: Int?,
        mouseLocation: CGPoint?
    ) -> Int? {
        guard !screens.isEmpty else { return nil }

        if let cgFrame = frontmostWindowCGFrame, cgFrame.width > 0, cgFrame.height > 0 {
            // CoreGraphics 座標はプライマリ画面（screens[0]）の左上が原点で Y 下向きのため AppKit 座標へ変換する。
            let primaryMaxY = screens[0].frame.maxY
            let appKitRect = CGRect(
                x: cgFrame.minX,
                y: primaryMaxY - cgFrame.maxY,
                width: cgFrame.width,
                height: cgFrame.height
            )
            let center = CGPoint(x: appKitRect.midX, y: appKitRect.midY)
            if let containingIndex = screens.firstIndex(where: { $0.frame.contains(center) }) {
                return containingIndex
            }
            var bestIndex: Int?
            var bestArea: CGFloat = 0
            for (index, screen) in screens.enumerated() {
                let intersection = screen.frame.intersection(appKitRect)
                if !intersection.isNull {
                    let area = intersection.width * intersection.height
                    if area > bestArea {
                        bestArea = area
                        bestIndex = index
                    }
                }
            }
            if let bestIndex {
                return bestIndex
            }
        }

        if let mainScreenIndex, screens.indices.contains(mainScreenIndex) {
            return mainScreenIndex
        }

        if let mouseLocation,
           let mouseIndex = screens.firstIndex(where: { $0.frame.contains(mouseLocation) }) {
            return mouseIndex
        }

        return 0
    }

    /// 影余白を含むパネル全体が、対象スクリーンの下中央（Dock 上端 + 14pt）へピル下端を合わせるウィンドウフレームを返す。
    public static func panelFrame(
        canvasSize: CGSize,
        bottomInset: CGFloat,
        in visibleFrame: CGRect
    ) -> CGRect {
        let originX = round(visibleFrame.midX - canvasSize.width / 2.0)
        let originY = round(visibleFrame.minY + OverlayMetrics.bottomMarginAboveDock - bottomInset)
        return CGRect(x: originX, y: originY, width: canvasSize.width, height: canvasSize.height)
    }

    /// 固定キャンバス内でピル本体を下中央アンカーへ配置するフレームを返す（高さ増加時は上方向へ広がる）。
    public static func pillFrameInCanvas(
        pillSize: CGSize,
        canvasSize: CGSize,
        bottomInset: CGFloat
    ) -> CGRect {
        let originX = round((canvasSize.width - pillSize.width) / 2.0)
        return CGRect(x: originX, y: bottomInset, width: pillSize.width, height: pillSize.height)
    }

    /// 途中結果のテキスト計測高さから、partial 展開時のピルサイズ（幅300pt・最小高さ60pt）を計算する。
    public static func partialPillSize(measuredTextHeight: CGFloat) -> CGSize {
        let maxTwoLineHeight = ceil(OverlayMetrics.partialLineHeight * CGFloat(OverlayMetrics.partialMaxLines))
        let clampedTextHeight = max(
            ceil(OverlayMetrics.partialLineHeight),
            min(ceil(measuredTextHeight), maxTwoLineHeight)
        )
        let contentHeight = OverlayMetrics.partialVerticalPadding
            + clampedTextHeight
            + OverlayMetrics.partialDividerBottomPadding
            + OverlayMetrics.dividerHeight
            + OverlayMetrics.partialSectionGap
            + OverlayMetrics.waveBarContainerHeight
            + OverlayMetrics.partialVerticalPadding
        let height = max(OverlayMetrics.partialRecordingMinHeight, ceil(contentHeight))
        return CGSize(width: OverlayMetrics.partialRecordingWidth, height: height)
    }

    /// エラー文言の計測幅から、エラー時のピルサイズ（高さ32pt・最大幅248pt）を計算する。
    public static func errorPillSize(measuredTextWidth: CGFloat) -> CGSize {
        let rawWidth = OverlayMetrics.compactHorizontalPadding * 2
            + OverlayMetrics.errorIconSize
            + OverlayMetrics.errorRowGap
            + ceil(max(0, measuredTextWidth))
        let clampedWidth = min(OverlayMetrics.errorMaxWidth, rawWidth)
        return CGSize(width: clampedWidth, height: OverlayMetrics.errorHeight)
    }
}
