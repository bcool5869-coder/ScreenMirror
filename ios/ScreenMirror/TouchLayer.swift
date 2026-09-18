import SwiftUI
import UIKit

enum FingerPhase: UInt8 {
    case down = 0, move = 1, up = 2
}

/// Transparent layer over the picture that reports every finger, as 0-1 coordinates
/// across the picture itself (not the black bars around it).
struct TouchLayer: UIViewRepresentable {
    let imageSize: CGSize
    let onFinger: (FingerPhase, UInt8, CGPoint) -> Void

    func makeUIView(context: Context) -> TouchView {
        let view = TouchView()
        view.isMultipleTouchEnabled = true
        view.backgroundColor = .clear
        return view
    }

    func updateUIView(_ view: TouchView, context: Context) {
        view.imageSize = imageSize
        view.onFinger = onFinger
    }
}

final class TouchView: UIView {
    var imageSize: CGSize = .zero
    var onFinger: ((FingerPhase, UInt8, CGPoint) -> Void)?
    private var ids: [ObjectIdentifier: UInt8] = [:]  // finger -> small id the PC uses

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        for touch in touches {
            guard let id = (UInt8(0)..<10).first(where: { !ids.values.contains($0) }) else { continue }
            ids[ObjectIdentifier(touch)] = id
            report(touch, .down)
        }
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        touches.forEach { report($0, .move) }
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        for touch in touches {
            report(touch, .up)
            ids[ObjectIdentifier(touch)] = nil
        }
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        touchesEnded(touches, with: event)
    }

    private func report(_ touch: UITouch, _ phase: FingerPhase) {
        guard let id = ids[ObjectIdentifier(touch)], imageSize.width > 0, imageSize.height > 0 else { return }
        // where the aspect-fit picture sits inside this view
        let scale = min(bounds.width / imageSize.width, bounds.height / imageSize.height)
        let w = imageSize.width * scale, h = imageSize.height * scale
        let p = touch.location(in: self)
        let x = min(max((p.x - (bounds.width - w) / 2) / w, 0), 1)
        let y = min(max((p.y - (bounds.height - h) / 2) / h, 0), 1)
        onFinger?(phase, id, CGPoint(x: x, y: y))
    }
}
