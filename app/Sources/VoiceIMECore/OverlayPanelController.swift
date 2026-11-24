import AppKit
import CoreGraphics
import Foundation
import QuartzCore

/// フォーカスとクリックを奪わずに最前面へ表示するオーバーレイ用 `NSPanel`。
@MainActor
public final class OverlayPanel: NSPanel {
    /// オーバーレイパネルに必須のスタイルマスク（枠なし・非アクティブ化パネル）。
    public static let requiredStyleMask: NSWindow.StyleMask = [.borderless, .nonactivatingPanel]
    /// 全操作スペースとフルスクリーン補助を含む必須のコレクション挙動。
    public static let requiredCollectionBehavior: NSWindow.CollectionBehavior = [
        .canJoinAllSpaces,
        .fullScreenAuxiliary,
        .stationary,
        .ignoresCycle,
    ]

    public init(contentRect: NSRect) {
        super.init(
            contentRect: contentRect,
            styleMask: Self.requiredStyleMask,
            backing: .buffered,
            defer: false
        )
        isFloatingPanel = true
        level = .floating
        collectionBehavior = Self.requiredCollectionBehavior
        ignoresMouseEvents = true
        hidesOnDeactivate = false
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        isReleasedWhenClosed = false
        animationBehavior = .none
    }

    public override var canBecomeKey: Bool { false }
    public override var canBecomeMain: Bool { false }

    /// 影余白の分だけ画面下端を越える配置でも、macOS による自動押し戻しでピル位置がズレないようにする。
    public override func constrainFrameRect(_ frameRect: NSRect, to screen: NSScreen?) -> NSRect {
        frameRect
    }
}

/// 画面下中央ピル（案A）の `NSPanel` のライフサイクル・配置・アニメーション・音量波形更新を担うコントローラ。
@MainActor
public final class OverlayPanelController: NSObject {
    private static let horizontalShadowPadding: CGFloat = 48
    private static let topShadowPadding: CGFloat = 36
    private static let bottomShadowPadding: CGFloat = 56
    private static let maxPillHeightBudget: CGFloat = 84
    private static let canvasSize = CGSize(
        width: OverlayMetrics.partialRecordingWidth + horizontalShadowPadding * 2,
        height: maxPillHeightBudget + topShadowPadding + bottomShadowPadding
    )

    private var panel: OverlayPanel?
    private var canvasView: OverlayCanvasView?
    private var currentState: OverlayState = .hidden
    private var isObservingScreenChanges = false

    public override init() {
        super.init()
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    /// オーバーレイの表示状態を反映し、必要に応じて表示・リサイズ・フェードアウトを行う。
    public func update(state: OverlayState) {
        let previousState = currentState
        currentState = state

        if case .hidden = state {
            guard let panel, let canvasView, panel.isVisible else {
                canvasView?.stopRecordingAnimations()
                return
            }
            let useDoneFade: Bool
            if case .done = previousState {
                useDoneFade = true
            } else {
                useDoneFade = false
            }
            canvasView.animateHide(isDoneFade: useDoneFade) { [weak panel] in
                panel?.orderOut(nil)
            }
            return
        }

        let (panel, canvasView) = ensurePanel()
        let wasVisible = panel.isVisible && previousState.isVisible
        if !wasVisible {
            repositionPanelOnFrontmostScreen(panel)
        }
        canvasView.apply(state: state, animated: wasVisible)
        if !panel.isVisible {
            canvasView.prepareForShowAnimation()
            panel.orderFrontRegardless()
            canvasView.animateShow()
        } else if !previousState.isVisible {
            // フェードアウト途中に新しい状態が来た場合は可視状態へ即時復帰させる。
            panel.orderFrontRegardless()
            canvasView.animateShow()
        }
    }

    /// 録音中の正規化音量レベル（0.0〜1.0）を波形バーへ反映する。
    public func updateAudioLevel(_ level: Float) {
        canvasView?.setAudioLevel(level)
    }

    /// アプリ終了時などにアニメーションなしで即座にパネルを閉じる。
    public func hideImmediately() {
        currentState = .hidden
        canvasView?.stopRecordingAnimations()
        panel?.orderOut(nil)
    }

    private func ensurePanel() -> (OverlayPanel, OverlayCanvasView) {
        if let panel, let canvasView {
            return (panel, canvasView)
        }
        let initialRect = NSRect(origin: .zero, size: Self.canvasSize)
        let panel = OverlayPanel(contentRect: initialRect)
        let canvas = OverlayCanvasView(
            frame: initialRect,
            bottomInset: Self.bottomShadowPadding
        )
        panel.contentView = canvas
        self.panel = panel
        self.canvasView = canvas

        if !isObservingScreenChanges {
            isObservingScreenChanges = true
            NotificationCenter.default.addObserver(
                self,
                selector: #selector(handleScreenParametersDidChange),
                name: NSApplication.didChangeScreenParametersNotification,
                object: nil
            )
        }
        return (panel, canvas)
    }

    @objc private func handleScreenParametersDidChange() {
        guard let panel, panel.isVisible else { return }
        repositionPanelOnFrontmostScreen(panel)
    }

    private func repositionPanelOnFrontmostScreen(_ panel: OverlayPanel) {
        let screens = NSScreen.screens
        guard !screens.isEmpty else { return }
        let geometries = screens.map {
            OverlayPanelLayout.ScreenGeometry(frame: $0.frame, visibleFrame: $0.visibleFrame)
        }
        let mainIndex = NSScreen.main.flatMap { main in screens.firstIndex(of: main) }
        let targetIndex = OverlayPanelLayout.selectScreenIndex(
            screens: geometries,
            frontmostWindowCGFrame: Self.frontmostWindowCGFrame(),
            mainScreenIndex: mainIndex,
            mouseLocation: NSEvent.mouseLocation
        ) ?? 0
        let targetScreen = screens[targetIndex]
        let frame = OverlayPanelLayout.panelFrame(
            canvasSize: Self.canvasSize,
            bottomInset: Self.bottomShadowPadding,
            in: targetScreen.visibleFrame
        )
        panel.setFrame(frame, display: true)
    }

    private static func frontmostWindowCGFrame() -> CGRect? {
        guard let frontApp = NSWorkspace.shared.frontmostApplication else {
            return nil
        }
        let pid = frontApp.processIdentifier
        guard pid > 0, pid != ProcessInfo.processInfo.processIdentifier else {
            return nil
        }
        guard let windowInfoList = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements],
            kCGNullWindowID
        ) as? [[String: Any]] else {
            return nil
        }
        for info in windowInfoList {
            guard let ownerPid = info[kCGWindowOwnerPID as String] as? pid_t,
                  ownerPid == pid,
                  let layer = info[kCGWindowLayer as String] as? Int,
                  layer == 0,
                  let boundsDict = info[kCGWindowBounds as String] as? NSDictionary,
                  let rect = CGRect(dictionaryRepresentation: boundsDict),
                  rect.width > 0,
                  rect.height > 0 else {
                continue
            }
            return rect
        }
        return nil
    }
}

// MARK: - Canvas & Pill Views

/// 影余白を含む固定サイズキャンバス内で、ピル本体を下中央アンカーで配置・アニメーションするコンテナ。
@MainActor
private final class OverlayCanvasView: NSView {
    private let bottomInset: CGFloat
    private let pillView: OverlayPillView
    private var visibilityGeneration: UInt64 = 0

    init(frame: NSRect, bottomInset: CGFloat) {
        self.bottomInset = bottomInset
        self.pillView = OverlayPillView(frame: .zero)
        super.init(frame: frame)
        wantsLayer = true
        layer?.masksToBounds = false
        addSubview(pillView)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func apply(state: OverlayState, animated: Bool) {
        visibilityGeneration &+= 1
        pillView.apply(state: state)
        let targetSize = pillView.preferredSize(for: state)
        let targetFrame = OverlayPanelLayout.pillFrameInCanvas(
            pillSize: targetSize,
            canvasSize: bounds.size,
            bottomInset: bottomInset
        )

        if animated {
            let duration = OverlayMetrics.stateTransitionDuration
            let timing = CAMediaTimingFunction(name: .easeInEaseOut)
            pillView.animateShadowTransition(to: CGRect(origin: .zero, size: targetSize), duration: duration, timing: timing)
            NSAnimationContext.runAnimationGroup { context in
                context.duration = duration
                context.timingFunction = timing
                context.allowsImplicitAnimation = true
                pillView.animator().frame = targetFrame
            }
        } else {
            pillView.frame = targetFrame
            pillView.layoutSubtreeIfNeeded()
        }
    }

    func setAudioLevel(_ level: Float) {
        pillView.setAudioLevel(level)
    }

    func stopRecordingAnimations() {
        pillView.stopRecordingAnimations()
    }

    func prepareForShowAnimation() {
        visibilityGeneration &+= 1
        pillView.layer?.removeAllAnimations()
        pillView.alphaValue = 0
        pillView.layer?.transform = Self.centeredTransform(scale: 0.94, translateY: -4, in: pillView.bounds)
    }

    func animateShow() {
        visibilityGeneration &+= 1
        let timing = CAMediaTimingFunction(controlPoints: 0.22, 1.0, 0.36, 1.0)
        NSAnimationContext.runAnimationGroup { context in
            context.duration = OverlayMetrics.showHideAnimationDuration
            context.timingFunction = timing
            pillView.animator().alphaValue = 1.0
        }
        if let pillLayer = pillView.layer {
            let anim = CABasicAnimation(keyPath: "transform")
            anim.fromValue = pillLayer.presentation()?.transform ?? pillLayer.transform
            anim.toValue = CATransform3DIdentity
            anim.duration = OverlayMetrics.showHideAnimationDuration
            anim.timingFunction = timing
            pillLayer.transform = CATransform3DIdentity
            pillLayer.add(anim, forKey: "overlayShowTransform")
        }
    }

    func animateHide(isDoneFade: Bool, completion: @escaping @MainActor () -> Void) {
        visibilityGeneration &+= 1
        let expectedGen = visibilityGeneration
        let duration = isDoneFade
            ? OverlayMetrics.doneFadeOutDuration
            : OverlayMetrics.showHideAnimationDuration
        let targetScale: CGFloat = isDoneFade ? 0.90 : 0.94
        let targetTranslateY: CGFloat = isDoneFade ? 0 : -4
        let timing = CAMediaTimingFunction(name: .easeInEaseOut)

        if let pillLayer = pillView.layer {
            let targetTransform = Self.centeredTransform(
                scale: targetScale,
                translateY: targetTranslateY,
                in: pillView.bounds
            )
            let anim = CABasicAnimation(keyPath: "transform")
            anim.fromValue = pillLayer.presentation()?.transform ?? pillLayer.transform
            anim.toValue = targetTransform
            anim.duration = duration
            anim.timingFunction = timing
            pillLayer.transform = targetTransform
            pillLayer.add(anim, forKey: "overlayHideTransform")
        }

        NSAnimationContext.runAnimationGroup({ context in
            context.duration = duration
            context.timingFunction = timing
            pillView.animator().alphaValue = 0
        }, completionHandler: { [weak self] in
            Task { @MainActor [weak self] in
                guard let self, self.visibilityGeneration == expectedGen else { return }
                self.pillView.stopRecordingAnimations()
                self.pillView.layer?.transform = CATransform3DIdentity
                completion()
            }
        })
    }

    /// `anchorPoint = (0, 0)` の NSView レイヤーに対して、ビュー中心を基準とした拡大縮小と平行移動行列を作る。
    private static func centeredTransform(scale: CGFloat, translateY: CGFloat, in bounds: CGRect) -> CATransform3D {
        let cx = bounds.midX
        let cy = bounds.midY
        var t = CATransform3DIdentity
        t = CATransform3DTranslate(t, cx, cy + translateY, 0)
        t = CATransform3DScale(t, scale, scale, 1)
        t = CATransform3DTranslate(t, -cx, -cy, 0)
        return t
    }
}

/// 試作 `.pill-a` の外観（フロストガラス・2段影・枠線・ティント）と全状態コンテンツを描画するビュー。
@MainActor
private final class OverlayPillView: NSView {
    private var currentState: OverlayState = .hidden
    private var currentPalette: OverlayThemePalette = .light
    private var lastPartialRevision: Int = -1

    // 背景と2段影（内側をくり抜いて半透明ピルの濁りを防ぐ）
    private let shadowContainerLayer = CALayer()
    private let shadowCutoutMaskLayer = CAShapeLayer()
    private let primaryShadowLayer = CALayer()
    private let secondaryShadowLayer = CALayer()

    private let visualEffectView = NSVisualEffectView()
    private let surfaceOverlayView = NSView()
    private let stateTintView = NSView()
    private let topHighlightView = NSView()
    private let contentClipView = NSView()
    private var suppressImmediateShadowPathUpdate = false

    // 録音中コンテンツ
    private let recordingContainer = NSView()
    private let partialLabel = NSTextField(wrappingLabelWithString: "")
    private let partialDividerView = NSView()
    private let recDotView = OverlayRecordingDotView()
    private let waveformView = OverlayWaveformBarsView()
    private let timerLabel = NSTextField(labelWithString: "0:00")

    // 処理中コンテンツ
    private let processingContainer = NSView()
    private let spinnerView = OverlaySpinnerView()
    private let processingLabel = NSTextField(labelWithString: OverlayMetrics.processingText)

    // 完了コンテンツ
    private let doneContainer = NSView()
    private let checkmarkView = OverlayCheckmarkView()

    // エラーコンテンツ
    private let errorContainer = NSView()
    private let errorIconView = OverlayErrorIconView()
    private let errorLabel = NSTextField(labelWithString: "")

    // 録音中のみ動かすタイマー（波形30fps・経過秒更新・partial最新語フェード）
    private var recordingFrameTimer: Timer?
    private var recordingStartTime: TimeInterval = 0
    private var lastDisplayedSecond: Int = -1
    private var targetAudioLevel: Double = 0
    private var smoothedAudioLevel: Double = 0
    private var lastAudioLevelTimestamp: TimeInterval = 0
    private var partialFadeStartTime: TimeInterval?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = false
        setupSurface()
        setupContentViews()
        applyTheme()
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        applyTheme()
    }

    override func layout() {
        super.layout()
        layoutSurfaceLayers()
        layoutActiveContent()
    }

    func apply(state: OverlayState) {
        let wasRecording: Bool
        if case .recording = currentState {
            wasRecording = true
        } else {
            wasRecording = false
        }
        currentState = state

        recordingContainer.isHidden = true
        processingContainer.isHidden = true
        doneContainer.isHidden = true
        errorContainer.isHidden = true

        switch state {
        case .hidden:
            stopRecordingAnimations()
            spinnerView.stopAnimating()

        case let .recording(recordingState):
            recordingContainer.isHidden = false
            spinnerView.stopAnimating()
            if !wasRecording {
                startRecordingAnimations()
            }
            if recordingState.hasPartial {
                partialLabel.isHidden = false
                partialDividerView.isHidden = false
                if recordingState.partialRevision != lastPartialRevision {
                    lastPartialRevision = recordingState.partialRevision
                    partialFadeStartTime = ProcessInfo.processInfo.systemUptime
                }
                updatePartialAttributedText(recordingState, latestAlphaMultiplier: partialFadeMultiplier())
            } else {
                partialLabel.isHidden = true
                partialDividerView.isHidden = true
                lastPartialRevision = -1
                partialFadeStartTime = nil
            }

        case .processing:
            stopRecordingAnimations()
            processingContainer.isHidden = false
            spinnerView.startAnimating()

        case .done:
            stopRecordingAnimations()
            spinnerView.stopAnimating()
            doneContainer.isHidden = false
            checkmarkView.playDrawAnimation()

        case let .error(message):
            stopRecordingAnimations()
            spinnerView.stopAnimating()
            errorContainer.isHidden = false
            errorLabel.stringValue = message
        }

        applyTheme()
        needsLayout = true
    }

    func setAudioLevel(_ level: Float) {
        targetAudioLevel = max(0.0, min(1.0, Double(level)))
        lastAudioLevelTimestamp = ProcessInfo.processInfo.systemUptime
    }

    func stopRecordingAnimations() {
        recordingFrameTimer?.invalidate()
        recordingFrameTimer = nil
        recDotView.stopPulse()
        targetAudioLevel = 0
        smoothedAudioLevel = 0
        partialFadeStartTime = nil
    }

    func preferredSize(for state: OverlayState) -> CGSize {
        switch state {
        case .hidden:
            return OverlayMetrics.doneSize
        case let .recording(recordingState):
            guard recordingState.hasPartial else {
                return OverlayMetrics.compactRecordingSize
            }
            let textWidth = OverlayMetrics.partialRecordingWidth - OverlayMetrics.partialHorizontalPadding * 2
            let measuredHeight = measurePartialTextHeight(recordingState, width: textWidth)
            return OverlayPanelLayout.partialPillSize(measuredTextHeight: measuredHeight)
        case .processing:
            return OverlayMetrics.processingSize
        case .done:
            return OverlayMetrics.doneSize
        case let .error(message):
            errorLabel.stringValue = message
            let fittingWidth = errorLabel.sizeThatFits(
                NSSize(width: CGFloat.greatestFiniteMagnitude, height: OverlayMetrics.errorHeight)
            ).width
            return OverlayPanelLayout.errorPillSize(measuredTextWidth: fittingWidth)
        }
    }

    // MARK: - Setup

    private func setupSurface() {
        shadowContainerLayer.masksToBounds = false
        shadowCutoutMaskLayer.fillRule = .evenOdd
        shadowContainerLayer.mask = shadowCutoutMaskLayer

        primaryShadowLayer.masksToBounds = false
        secondaryShadowLayer.masksToBounds = false
        shadowContainerLayer.addSublayer(primaryShadowLayer)
        shadowContainerLayer.addSublayer(secondaryShadowLayer)
        layer?.addSublayer(shadowContainerLayer)

        visualEffectView.material = .hudWindow
        visualEffectView.blendingMode = .behindWindow
        visualEffectView.state = .active
        visualEffectView.wantsLayer = true
        visualEffectView.layer?.cornerRadius = OverlayMetrics.cornerRadius
        visualEffectView.layer?.masksToBounds = true
        visualEffectView.autoresizingMask = [.width, .height]
        addSubview(visualEffectView)

        surfaceOverlayView.wantsLayer = true
        surfaceOverlayView.layer?.cornerRadius = OverlayMetrics.cornerRadius
        surfaceOverlayView.layer?.masksToBounds = true
        surfaceOverlayView.layer?.borderWidth = OverlayMetrics.borderWidth
        surfaceOverlayView.autoresizingMask = [.width, .height]
        addSubview(surfaceOverlayView)

        stateTintView.wantsLayer = true
        stateTintView.autoresizingMask = [.width, .height]
        surfaceOverlayView.addSubview(stateTintView)

        topHighlightView.wantsLayer = true
        topHighlightView.autoresizingMask = [.width, .minYMargin]
        surfaceOverlayView.addSubview(topHighlightView)

        contentClipView.wantsLayer = true
        contentClipView.layer?.cornerRadius = OverlayMetrics.cornerRadius
        contentClipView.layer?.masksToBounds = true
        contentClipView.autoresizingMask = [.width, .height]
        addSubview(contentClipView)
    }

    private func setupContentViews() {
        // 録音中ビュー
        recordingContainer.wantsLayer = true
        recordingContainer.layer?.masksToBounds = false
        contentClipView.addSubview(recordingContainer)

        partialLabel.isEditable = false
        partialLabel.isSelectable = false
        partialLabel.isBezeled = false
        partialLabel.drawsBackground = false
        partialLabel.usesSingleLineMode = false
        partialLabel.maximumNumberOfLines = OverlayMetrics.partialMaxLines
        partialLabel.lineBreakMode = .byWordWrapping
        partialLabel.cell?.wraps = true
        partialLabel.cell?.truncatesLastVisibleLine = true
        partialLabel.preferredMaxLayoutWidth =
            OverlayMetrics.partialRecordingWidth - OverlayMetrics.partialHorizontalPadding * 2
        recordingContainer.addSubview(partialLabel)

        partialDividerView.wantsLayer = true
        recordingContainer.addSubview(partialDividerView)
        recordingContainer.addSubview(recDotView)
        recordingContainer.addSubview(waveformView)

        timerLabel.isEditable = false
        timerLabel.isSelectable = false
        timerLabel.isBezeled = false
        timerLabel.drawsBackground = false
        timerLabel.alignment = .right
        timerLabel.font = NSFont.monospacedDigitSystemFont(
            ofSize: OverlayMetrics.timerFontSize,
            weight: .medium
        )
        recordingContainer.addSubview(timerLabel)

        // 処理中ビュー
        processingContainer.wantsLayer = true
        contentClipView.addSubview(processingContainer)
        processingContainer.addSubview(spinnerView)

        processingLabel.isEditable = false
        processingLabel.isSelectable = false
        processingLabel.isBezeled = false
        processingLabel.drawsBackground = false
        processingLabel.font = NSFont.systemFont(ofSize: OverlayMetrics.statusFontSize, weight: .medium)
        processingLabel.maximumNumberOfLines = 1
        processingLabel.lineBreakMode = .byTruncatingTail
        processingContainer.addSubview(processingLabel)

        // 完了ビュー
        doneContainer.wantsLayer = true
        contentClipView.addSubview(doneContainer)
        doneContainer.addSubview(checkmarkView)

        // エラービュー
        errorContainer.wantsLayer = true
        contentClipView.addSubview(errorContainer)
        errorContainer.addSubview(errorIconView)

        errorLabel.isEditable = false
        errorLabel.isSelectable = false
        errorLabel.isBezeled = false
        errorLabel.drawsBackground = false
        errorLabel.font = NSFont.systemFont(ofSize: OverlayMetrics.statusFontSize, weight: .medium)
        errorLabel.maximumNumberOfLines = 1
        errorLabel.lineBreakMode = .byTruncatingTail
        errorContainer.addSubview(errorLabel)
    }

    // MARK: - Layout

    func animateShadowTransition(to targetBounds: CGRect, duration: TimeInterval, timing: CAMediaTimingFunction) {
        let newPillPath = Self.pillRoundedPath(in: targetBounds)
        let newCutoutPath = Self.shadowCutoutPath(for: targetBounds, pillPath: newPillPath)

        for shadowLayer in [primaryShadowLayer, secondaryShadowLayer] {
            let anim = CABasicAnimation(keyPath: "shadowPath")
            anim.fromValue = shadowLayer.presentation()?.shadowPath ?? shadowLayer.shadowPath
            anim.toValue = newPillPath
            anim.duration = duration
            anim.timingFunction = timing
            shadowLayer.shadowPath = newPillPath
            shadowLayer.add(anim, forKey: "shadowPathResize")
        }

        let maskAnim = CABasicAnimation(keyPath: "path")
        maskAnim.fromValue = shadowCutoutMaskLayer.presentation()?.path ?? shadowCutoutMaskLayer.path
        maskAnim.toValue = newCutoutPath
        maskAnim.duration = duration
        maskAnim.timingFunction = timing
        shadowCutoutMaskLayer.path = newCutoutPath
        shadowCutoutMaskLayer.add(maskAnim, forKey: "maskPathResize")

        suppressImmediateShadowPathUpdate = true
    }

    private static func pillRoundedPath(in rect: CGRect) -> CGPath {
        CGPath(
            roundedRect: rect,
            cornerWidth: OverlayMetrics.cornerRadius,
            cornerHeight: OverlayMetrics.cornerRadius,
            transform: nil
        )
    }

    private static func shadowCutoutPath(for rect: CGRect, pillPath: CGPath) -> CGPath {
        let cutoutRect = rect.insetBy(dx: -80, dy: -80)
        let cutoutPath = CGMutablePath()
        cutoutPath.addRect(cutoutRect)
        cutoutPath.addPath(pillPath)
        return cutoutPath
    }

    private func layoutSurfaceLayers() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)

        let pillBounds = bounds
        shadowContainerLayer.frame = pillBounds
        shadowCutoutMaskLayer.frame = pillBounds
        primaryShadowLayer.frame = pillBounds
        secondaryShadowLayer.frame = pillBounds

        if suppressImmediateShadowPathUpdate {
            suppressImmediateShadowPathUpdate = false
        } else {
            let pillPath = Self.pillRoundedPath(in: pillBounds)
            // 影はピル外側のみへ描き、半透明のピル背景へ影の塗りが透けないように内側をくり抜く。
            shadowCutoutMaskLayer.path = Self.shadowCutoutPath(for: pillBounds, pillPath: pillPath)
            primaryShadowLayer.shadowPath = pillPath
            secondaryShadowLayer.shadowPath = pillPath
        }

        visualEffectView.frame = pillBounds
        surfaceOverlayView.frame = pillBounds
        stateTintView.frame = pillBounds
        topHighlightView.frame = CGRect(
            x: 0,
            y: pillBounds.height - OverlayMetrics.topHighlightHeight,
            width: pillBounds.width,
            height: OverlayMetrics.topHighlightHeight
        )
        contentClipView.frame = pillBounds

        CATransaction.commit()
    }

    private func layoutActiveContent() {
        let pillBounds = bounds
        recordingContainer.frame = pillBounds
        processingContainer.frame = pillBounds
        doneContainer.frame = pillBounds
        errorContainer.frame = pillBounds

        switch currentState {
        case .hidden:
            break

        case let .recording(recordingState):
            let hasPartial = recordingState.hasPartial
            let horizontalPadding = hasPartial
                ? OverlayMetrics.partialHorizontalPadding
                : OverlayMetrics.compactHorizontalPadding
            let rowCenterY: CGFloat = hasPartial
                ? OverlayMetrics.partialVerticalPadding + OverlayMetrics.waveBarContainerHeight / 2.0
                : pillBounds.height / 2.0

            let dotX = horizontalPadding
            recDotView.frame = CGRect(
                x: dotX,
                y: round(rowCenterY - OverlayMetrics.recDotSize / 2.0),
                width: OverlayMetrics.recDotSize,
                height: OverlayMetrics.recDotSize
            )

            let waveWidth = CGFloat(OverlayMetrics.waveBarCount) * OverlayMetrics.waveBarWidth
                + CGFloat(OverlayMetrics.waveBarCount - 1) * OverlayMetrics.waveBarGap
            let waveX = dotX + OverlayMetrics.recDotSize + OverlayMetrics.rowGap
            waveformView.frame = CGRect(
                x: waveX,
                y: round(rowCenterY - OverlayMetrics.waveBarContainerHeight / 2.0),
                width: waveWidth,
                height: OverlayMetrics.waveBarContainerHeight
            )

            let timerFitting = timerLabel.sizeThatFits(NSSize(width: 80, height: 24))
            let timerWidth = max(OverlayMetrics.timerMinWidth, ceil(timerFitting.width))
            let timerHeight = ceil(timerFitting.height)
            let timerX = pillBounds.width - horizontalPadding - timerWidth
            timerLabel.frame = CGRect(
                x: timerX,
                y: round(rowCenterY - timerHeight / 2.0),
                width: timerWidth,
                height: timerHeight
            )

            if hasPartial {
                let dividerY = OverlayMetrics.partialVerticalPadding
                    + OverlayMetrics.waveBarContainerHeight
                    + OverlayMetrics.partialSectionGap
                let contentWidth = pillBounds.width - horizontalPadding * 2
                partialDividerView.frame = CGRect(
                    x: horizontalPadding,
                    y: dividerY,
                    width: contentWidth,
                    height: OverlayMetrics.dividerHeight
                )
                let textY = dividerY + OverlayMetrics.dividerHeight + OverlayMetrics.partialDividerBottomPadding
                let textHeight = max(0, pillBounds.height - OverlayMetrics.partialVerticalPadding - textY)
                partialLabel.preferredMaxLayoutWidth = contentWidth
                partialLabel.frame = CGRect(
                    x: horizontalPadding,
                    y: textY,
                    width: contentWidth,
                    height: textHeight
                )
            }

        case .processing:
            let spinnerX = OverlayMetrics.compactHorizontalPadding
            spinnerView.frame = CGRect(
                x: spinnerX,
                y: round((pillBounds.height - OverlayMetrics.spinnerSize) / 2.0),
                width: OverlayMetrics.spinnerSize,
                height: OverlayMetrics.spinnerSize
            )
            let labelX = spinnerX + OverlayMetrics.spinnerSize + OverlayMetrics.rowGap
            let labelWidth = max(0, pillBounds.width - labelX - OverlayMetrics.compactHorizontalPadding)
            let labelHeight = ceil(processingLabel.sizeThatFits(NSSize(width: labelWidth, height: 24)).height)
            processingLabel.frame = CGRect(
                x: labelX,
                y: round((pillBounds.height - labelHeight) / 2.0),
                width: labelWidth,
                height: labelHeight
            )

        case .done:
            checkmarkView.frame = CGRect(
                x: round((pillBounds.width - OverlayMetrics.checkIconSize) / 2.0),
                y: round((pillBounds.height - OverlayMetrics.checkIconSize) / 2.0),
                width: OverlayMetrics.checkIconSize,
                height: OverlayMetrics.checkIconSize
            )

        case .error:
            let iconX = OverlayMetrics.compactHorizontalPadding
            errorIconView.frame = CGRect(
                x: iconX,
                y: round((pillBounds.height - OverlayMetrics.errorIconSize) / 2.0),
                width: OverlayMetrics.errorIconSize,
                height: OverlayMetrics.errorIconSize
            )
            let labelX = iconX + OverlayMetrics.errorIconSize + OverlayMetrics.errorRowGap
            let labelWidth = max(0, pillBounds.width - labelX - OverlayMetrics.compactHorizontalPadding)
            let labelHeight = ceil(errorLabel.sizeThatFits(NSSize(width: labelWidth, height: 24)).height)
            errorLabel.frame = CGRect(
                x: labelX,
                y: round((pillBounds.height - labelHeight) / 2.0),
                width: labelWidth,
                height: labelHeight
            )
        }
    }

    // MARK: - Theme

    private func applyTheme() {
        let isDark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let palette: OverlayThemePalette = isDark ? .dark : .light
        currentPalette = palette

        CATransaction.begin()
        CATransaction.setDisableActions(true)

        applyShadow(palette.primaryShadow, to: primaryShadowLayer)
        applyShadow(palette.secondaryShadow, to: secondaryShadowLayer)

        surfaceOverlayView.layer?.backgroundColor = palette.hudBackground.cgColor

        switch currentState {
        case .done:
            stateTintView.layer?.backgroundColor = palette.sysGreenTint.cgColor
            surfaceOverlayView.layer?.borderColor = palette.doneBorder.cgColor
            topHighlightView.isHidden = true
        case .error:
            stateTintView.layer?.backgroundColor = palette.sysRedTint.cgColor
            surfaceOverlayView.layer?.borderColor = palette.sysRedBorder.cgColor
            topHighlightView.isHidden = true
        case .hidden, .recording, .processing:
            stateTintView.layer?.backgroundColor = NSColor.clear.cgColor
            surfaceOverlayView.layer?.borderColor = palette.hudBorder.cgColor
            topHighlightView.layer?.backgroundColor = palette.hudHighlight.cgColor
            topHighlightView.isHidden = false
        }

        partialDividerView.layer?.backgroundColor = palette.hudDivider.cgColor
        CATransaction.commit()

        recDotView.applyPalette(palette)
        waveformView.applyPalette(palette)
        timerLabel.textColor = palette.hudTextMuted.nsColor
        spinnerView.applyPalette(palette)
        processingLabel.textColor = palette.hudText.nsColor
        checkmarkView.applyPalette(palette)
        errorIconView.applyPalette(palette)
        errorLabel.textColor = palette.sysRedText.nsColor

        if case let .recording(recordingState) = currentState, recordingState.hasPartial {
            updatePartialAttributedText(recordingState, latestAlphaMultiplier: partialFadeMultiplier())
        }
    }

    private func applyShadow(_ spec: OverlayShadowSpec, to layer: CALayer) {
        layer.shadowColor = NSColor.black.cgColor
        layer.shadowOpacity = Float(spec.alpha)
        // AppKit の非反転座標では下向きの影は負の height。
        layer.shadowOffset = CGSize(width: 0, height: -spec.offsetY)
        layer.shadowRadius = spec.blurRadius / 2.0
    }

    // MARK: - Recording Loop & Text Formatting

    private func startRecordingAnimations() {
        recordingStartTime = ProcessInfo.processInfo.systemUptime
        lastDisplayedSecond = 0
        targetAudioLevel = 0
        smoothedAudioLevel = 0
        lastAudioLevelTimestamp = recordingStartTime
        timerLabel.stringValue = OverlayAudioLevel.formatElapsed(seconds: 0)
        recDotView.startPulse()
        waveformView.update(envelope: 0, timeSeconds: 0)

        recordingFrameTimer?.invalidate()
        let timer = Timer(timeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.tickRecordingFrame()
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        recordingFrameTimer = timer
    }

    private func tickRecordingFrame() {
        guard case let .recording(recordingState) = currentState else {
            stopRecordingAnimations()
            return
        }
        let now = ProcessInfo.processInfo.systemUptime
        let elapsed = max(0, now - recordingStartTime)
        let wholeSeconds = Int(elapsed)
        if wholeSeconds != lastDisplayedSecond {
            lastDisplayedSecond = wholeSeconds
            timerLabel.stringValue = OverlayAudioLevel.formatElapsed(seconds: wholeSeconds)
        }

        // 音声サンプルが一定時間届いていない場合は無音へ向かって減衰させる。
        let activeTarget = (now - lastAudioLevelTimestamp > 0.25) ? 0.0 : targetAudioLevel
        let smoothing = activeTarget > smoothedAudioLevel ? 0.45 : 0.22
        smoothedAudioLevel += (activeTarget - smoothedAudioLevel) * smoothing
        if smoothedAudioLevel < 0.005 {
            smoothedAudioLevel = 0
        }
        waveformView.update(envelope: smoothedAudioLevel, timeSeconds: elapsed)

        if recordingState.hasPartial, partialFadeStartTime != nil {
            let multiplier = partialFadeMultiplier()
            updatePartialAttributedText(recordingState, latestAlphaMultiplier: multiplier)
            if multiplier >= 1.0 {
                partialFadeStartTime = nil
            }
        }
    }

    private func partialFadeMultiplier() -> CGFloat {
        guard let start = partialFadeStartTime else { return 1.0 }
        let progress = (ProcessInfo.processInfo.systemUptime - start) / OverlayMetrics.partialChunkFadeDuration
        if progress >= 1.0 {
            return 1.0
        }
        let clamped = max(0.0, progress)
        // 試作 `@keyframes chunkFadeIn { from { opacity: 0.25; } to { opacity: 1; } }`
        return CGFloat(0.25 + 0.75 * clamped)
    }

    private func buildPartialAttributedString(
        _ recordingState: OverlayRecordingState,
        latestAlphaMultiplier: CGFloat
    ) -> NSAttributedString {
        let paragraphStyle = NSMutableParagraphStyle()
        paragraphStyle.minimumLineHeight = OverlayMetrics.partialLineHeight
        paragraphStyle.maximumLineHeight = OverlayMetrics.partialLineHeight
        paragraphStyle.lineBreakMode = .byWordWrapping

        let font = NSFont.systemFont(ofSize: OverlayMetrics.partialFontSize, weight: .regular)
        let result = NSMutableAttributedString()

        if !recordingState.partialPrefix.isEmpty {
            result.append(
                NSAttributedString(
                    string: recordingState.partialPrefix,
                    attributes: [
                        .font: font,
                        .foregroundColor: currentPalette.hudTextMuted.nsColor,
                        .paragraphStyle: paragraphStyle,
                    ]
                )
            )
        }
        if !recordingState.partialLatest.isEmpty {
            let latestColor = currentPalette.hudText.nsColor.withAlphaComponent(
                currentPalette.hudText.alpha * latestAlphaMultiplier
            )
            result.append(
                NSAttributedString(
                    string: recordingState.partialLatest,
                    attributes: [
                        .font: font,
                        .foregroundColor: latestColor,
                        .paragraphStyle: paragraphStyle,
                    ]
                )
            )
        }
        return result
    }

    private func updatePartialAttributedText(
        _ recordingState: OverlayRecordingState,
        latestAlphaMultiplier: CGFloat
    ) {
        partialLabel.attributedStringValue = buildPartialAttributedString(
            recordingState,
            latestAlphaMultiplier: latestAlphaMultiplier
        )
    }

    private func measurePartialTextHeight(_ recordingState: OverlayRecordingState, width: CGFloat) -> CGFloat {
        // NSTextField 自身のセル余白と最大2行制限を反映した実描画高さを測る。
        partialLabel.preferredMaxLayoutWidth = width
        partialLabel.attributedStringValue = buildPartialAttributedString(
            recordingState,
            latestAlphaMultiplier: partialFadeMultiplier()
        )
        let fitting = partialLabel.sizeThatFits(
            NSSize(width: width, height: CGFloat.greatestFiniteMagnitude)
        )
        return ceil(fitting.height)
    }
}

// MARK: - Subcomponents

/// 録音中の赤い脈動ドット（直径8pt、外周に1.5s周期の脈動リング）。
@MainActor
private final class OverlayRecordingDotView: NSView {
    private let dotLayer = CALayer()
    private let pulseLayer = CAShapeLayer()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = false

        dotLayer.cornerRadius = OverlayMetrics.recDotSize / 2.0
        layer?.addSublayer(dotLayer)

        pulseLayer.fillColor = nil
        pulseLayer.lineWidth = OverlayMetrics.recPulseLineWidth
        pulseLayer.opacity = 0
        layer?.addSublayer(pulseLayer)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func layout() {
        super.layout()
        let size = OverlayMetrics.recDotSize
        dotLayer.frame = CGRect(x: 0, y: 0, width: size, height: size)

        let pulseDiameter = size + OverlayMetrics.recPulseInset * 2
        pulseLayer.bounds = CGRect(x: 0, y: 0, width: pulseDiameter, height: pulseDiameter)
        pulseLayer.position = CGPoint(x: size / 2.0, y: size / 2.0)
        pulseLayer.path = CGPath(
            ellipseIn: pulseLayer.bounds.insetBy(
                dx: OverlayMetrics.recPulseLineWidth / 2.0,
                dy: OverlayMetrics.recPulseLineWidth / 2.0
            ),
            transform: nil
        )
    }

    func applyPalette(_ palette: OverlayThemePalette) {
        dotLayer.backgroundColor = palette.sysRed.cgColor
        pulseLayer.strokeColor = palette.sysRed.cgColor
    }

    func startPulse() {
        pulseLayer.removeAllAnimations()
        let scale = CABasicAnimation(keyPath: "transform.scale")
        scale.fromValue = 0.75
        scale.toValue = 1.7

        let opacity = CABasicAnimation(keyPath: "opacity")
        opacity.fromValue = 0.7
        opacity.toValue = 0.0

        let group = CAAnimationGroup()
        group.animations = [scale, opacity]
        group.duration = OverlayMetrics.recPulseDuration
        group.timingFunction = CAMediaTimingFunction(name: .easeOut)
        group.repeatCount = .infinity
        pulseLayer.add(group, forKey: "recPulse")
    }

    func stopPulse() {
        pulseLayer.removeAllAnimations()
        pulseLayer.opacity = 0
    }
}

/// 音量に連動して高さ（4〜16pt）が変化する9本のカプセル型波形バー。
@MainActor
private final class OverlayWaveformBarsView: NSView {
    private var barLayers: [CALayer] = []

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        for _ in 0 ..< OverlayMetrics.waveBarCount {
            let bar = CALayer()
            bar.cornerRadius = OverlayMetrics.waveBarWidth / 2.0
            bar.anchorPoint = CGPoint(x: 0.5, y: 0.5)
            bar.bounds = CGRect(
                x: 0,
                y: 0,
                width: OverlayMetrics.waveBarWidth,
                height: OverlayMetrics.waveBarMinHeight
            )
            layer?.addSublayer(bar)
            barLayers.append(bar)
        }
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func layout() {
        super.layout()
        let step = OverlayMetrics.waveBarWidth + OverlayMetrics.waveBarGap
        let midY = bounds.height / 2.0
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        for (idx, bar) in barLayers.enumerated() {
            let centerX = CGFloat(idx) * step + OverlayMetrics.waveBarWidth / 2.0
            bar.position = CGPoint(x: centerX, y: midY)
        }
        CATransaction.commit()
    }

    func applyPalette(_ palette: OverlayThemePalette) {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        for bar in barLayers {
            bar.backgroundColor = palette.sysRed.cgColor
        }
        CATransaction.commit()
    }

    func update(envelope: Double, timeSeconds: Double) {
        let heights = OverlayAudioLevel.barHeights(envelope: envelope, timeSeconds: timeSeconds)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        for (idx, bar) in barLayers.enumerated() where idx < heights.count {
            bar.bounds = CGRect(
                x: 0,
                y: 0,
                width: OverlayMetrics.waveBarWidth,
                height: heights[idx]
            )
        }
        CATransaction.commit()
    }
}

/// 処理中のスピナー（直径14pt、線幅2pt、0.72秒周期で回転）。
@MainActor
private final class OverlaySpinnerView: NSView {
    private let trackLayer = CAShapeLayer()
    private let headLayer = CAShapeLayer()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true

        trackLayer.fillColor = nil
        trackLayer.lineWidth = OverlayMetrics.spinnerLineWidth
        layer?.addSublayer(trackLayer)

        headLayer.fillColor = nil
        headLayer.lineWidth = OverlayMetrics.spinnerLineWidth
        headLayer.strokeStart = 0
        headLayer.strokeEnd = 0.25
        layer?.addSublayer(headLayer)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func layout() {
        super.layout()
        let size = OverlayMetrics.spinnerSize
        let center = CGPoint(x: size / 2.0, y: size / 2.0)
        let radius = (size - OverlayMetrics.spinnerLineWidth) / 2.0
        let circlePath = CGMutablePath()
        // 上端（90度）から時計回り（非反転座標で角度減少方向）へ1周する円パス。
        circlePath.addArc(
            center: center,
            radius: radius,
            startAngle: .pi / 2.0,
            endAngle: .pi / 2.0 - .pi * 2.0,
            clockwise: true
        )

        trackLayer.frame = CGRect(x: 0, y: 0, width: size, height: size)
        trackLayer.path = circlePath

        headLayer.bounds = CGRect(x: 0, y: 0, width: size, height: size)
        headLayer.position = center
        headLayer.path = circlePath
    }

    func applyPalette(_ palette: OverlayThemePalette) {
        trackLayer.strokeColor = palette.spinnerTrack.cgColor
        headLayer.strokeColor = palette.spinnerHead.cgColor
    }

    func startAnimating() {
        guard headLayer.animation(forKey: "spin") == nil else { return }
        let anim = CABasicAnimation(keyPath: "transform.rotation.z")
        anim.fromValue = 0.0
        anim.toValue = -Double.pi * 2.0
        anim.duration = OverlayMetrics.spinnerRotationDuration
        anim.repeatCount = .infinity
        anim.timingFunction = CAMediaTimingFunction(name: .linear)
        headLayer.add(anim, forKey: "spin")
    }

    func stopAnimating() {
        headLayer.removeAnimation(forKey: "spin")
    }
}

/// 完了時の緑チェックマーク（16×16pt、240msでストローク描画）。
@MainActor
private final class OverlayCheckmarkView: NSView {
    private let checkLayer = CAShapeLayer()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true

        checkLayer.fillColor = nil
        checkLayer.lineWidth = OverlayMetrics.checkStrokeWidth
        checkLayer.lineCap = .round
        checkLayer.lineJoin = .round
        layer?.addSublayer(checkLayer)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func layout() {
        super.layout()
        checkLayer.frame = bounds
        // 試作 SVG `viewBox="0 0 16 16" d="M3.3 8.4L6.6 11.7L12.8 4.6"` を非反転（左下原点）座標へ変換して描く。
        let size = OverlayMetrics.checkIconSize
        let path = CGMutablePath()
        path.move(to: CGPoint(x: 3.3, y: size - 8.4))
        path.addLine(to: CGPoint(x: 6.6, y: size - 11.7))
        path.addLine(to: CGPoint(x: 12.8, y: size - 4.6))
        checkLayer.path = path
    }

    func applyPalette(_ palette: OverlayThemePalette) {
        checkLayer.strokeColor = palette.sysGreen.cgColor
    }

    func playDrawAnimation() {
        checkLayer.removeAllAnimations()
        let anim = CABasicAnimation(keyPath: "strokeEnd")
        anim.fromValue = 0.0
        anim.toValue = 1.0
        anim.duration = OverlayMetrics.checkDrawDuration
        anim.timingFunction = CAMediaTimingFunction(controlPoints: 0.22, 1.0, 0.36, 1.0)
        checkLayer.strokeEnd = 1.0
        checkLayer.add(anim, forKey: "drawCheck")
    }
}

/// エラー時の赤い三角警告アイコン（14×14pt、試作 SVG `errorTriangle` 準拠）。
@MainActor
private final class OverlayErrorIconView: NSView {
    private let triangleLayer = CAShapeLayer()
    private let stemLayer = CAShapeLayer()
    private let dotLayer = CAShapeLayer()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true

        layer?.addSublayer(triangleLayer)

        stemLayer.fillColor = nil
        stemLayer.strokeColor = NSColor.white.cgColor
        stemLayer.lineCap = .round
        layer?.addSublayer(stemLayer)

        dotLayer.fillColor = NSColor.white.cgColor
        layer?.addSublayer(dotLayer)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func layout() {
        super.layout()
        let scale = OverlayMetrics.errorIconSize / 16.0
        // SVG 左上原点（16×16）を非反転（左下原点）14×14pt へ変換する。
        func pt(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: x * scale, y: (16.0 - y) * scale)
        }

        // 試作 SVG `viewBox="0 0 16 16"` の角丸三角形パスを 14×14pt へスケール。
        let tri = CGMutablePath()
        tri.move(to: pt(7.15, 2.45))
        tri.addCurve(to: pt(8.85, 2.45), control1: pt(7.53, 1.78), control2: pt(8.47, 1.78))
        tri.addLine(to: pt(14.2, 11.95))
        tri.addCurve(to: pt(13.34, 13.45), control1: pt(14.58, 12.62), control2: pt(14.1, 13.45))
        tri.addLine(to: pt(2.66, 13.45))
        tri.addCurve(to: pt(1.8, 11.95), control1: pt(1.9, 13.45), control2: pt(1.42, 12.62))
        tri.closeSubpath()

        triangleLayer.frame = bounds
        triangleLayer.path = tri

        let stem = CGMutablePath()
        stem.move(to: pt(8.0, 5.6))
        stem.addLine(to: pt(8.0, 8.9))
        stemLayer.frame = bounds
        stemLayer.lineWidth = 1.5 * scale
        stemLayer.path = stem

        let dotRadius = 0.85 * scale
        let dotCenter = pt(8.0, 11.2)
        dotLayer.frame = bounds
        dotLayer.path = CGPath(
            ellipseIn: CGRect(
                x: dotCenter.x - dotRadius,
                y: dotCenter.y - dotRadius,
                width: dotRadius * 2,
                height: dotRadius * 2
            ),
            transform: nil
        )
    }

    func applyPalette(_ palette: OverlayThemePalette) {
        triangleLayer.fillColor = palette.sysRed.cgColor
    }
}

// MARK: - Color Helpers

private extension OverlayRGBAColor {
    var nsColor: NSColor {
        NSColor(srgbRed: red, green: green, blue: blue, alpha: alpha)
    }

    var cgColor: CGColor {
        nsColor.cgColor
    }
}
