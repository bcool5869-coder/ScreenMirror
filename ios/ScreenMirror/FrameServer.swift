import Foundation
import Network
import UIKit

/// Listens for the PC sender and shows the JPEG frames it streams.
///
/// The same listener serves both links: Wi-Fi connects to it directly, and the
/// cable reaches it through Apple's usbmux tunnel on the PC.
///
/// Wire format:
///   phone -> PC: one JSON line `{"w":…,"h":…}` (screen pixels, landscape), then messages:
///                0x01 = a frame was shown
///                0x02, phase, finger id, x, y (big-endian Float32, 0-1 across the picture) = a finger
///   PC -> phone: 4-byte big-endian length, then that many bytes of JPEG, repeated
final class FrameServer: ObservableObject {
    static let port: NWEndpoint.Port = 7700

    @Published var frame: UIImage?
    @Published var status = "Starting…"

    private var listener: NWListener?
    private var connection: NWConnection?
    private let queue = DispatchQueue(label: "screenmirror.net")
    private let screenPixels = UIScreen.main.nativeBounds.size

    func start() {
        guard listener == nil else { return }
        do {
            let params = NWParameters.tcp
            params.allowLocalEndpointReuse = true
            let listener = try NWListener(using: params, on: Self.port)
            listener.service = NWListener.Service(name: "ScreenMirror \(UIDevice.current.model)",
                                                  type: "_screenmirror._tcp")
            listener.stateUpdateHandler = { [weak self] state in
                if case .failed(let error) = state {
                    self?.show(status: "Listener failed: \(error)")
                }
            }
            listener.newConnectionHandler = { [weak self] conn in self?.accept(conn) }
            listener.start(queue: queue)
            self.listener = listener
            status = "Waiting for PC…"
        } catch {
            status = "Could not listen: \(error)"
        }
    }

    // Runs on `queue`. A new PC connection replaces the old one.
    private func accept(_ conn: NWConnection) {
        connection?.cancel()
        connection = conn
        conn.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready:
                self.sendHello(on: conn)
                self.readHeader(on: conn)
                self.show(status: "Connected")
            case .failed:
                conn.cancel()
            case .cancelled:
                conn.stateUpdateHandler = nil  // breaks the conn -> handler -> conn cycle
                if self.connection === conn {
                    self.connection = nil
                    DispatchQueue.main.async { self.frame = nil }
                    self.show(status: "Waiting for PC…")
                }
            default:
                break
            }
        }
        conn.start(queue: queue)
    }

    private func sendHello(on conn: NWConnection) {
        let w = Int(max(screenPixels.width, screenPixels.height))
        let h = Int(min(screenPixels.width, screenPixels.height))
        conn.send(content: Data("{\"w\":\(w),\"h\":\(h)}\n".utf8), completion: .idempotent)
    }

    private func readHeader(on conn: NWConnection) {
        conn.receive(minimumIncompleteLength: 4, maximumLength: 4) { [weak self] data, _, _, error in
            guard let self, error == nil, let data, data.count == 4 else { conn.cancel(); return }
            let length = data.reduce(0) { ($0 << 8) | Int($1) }
            guard length > 0, length < 20_000_000 else { conn.cancel(); return }
            self.readFrame(length, on: conn)
        }
    }

    private func readFrame(_ length: Int, on conn: NWConnection) {
        conn.receive(minimumIncompleteLength: length, maximumLength: length) { [weak self] data, _, _, error in
            guard let self, error == nil, let data, data.count == length else { conn.cancel(); return }
            // decode here, off the main thread, so drawing it is cheap
            if let image = UIImage(data: data)?.preparingForDisplay() {
                DispatchQueue.main.async { self.frame = image }
            }
            conn.send(content: Data([1]), completion: .idempotent)  // lets the PC send the next frame
            self.readHeader(on: conn)
        }
    }

    /// Called on the main thread by the touch layer.
    func sendFinger(_ phase: FingerPhase, id: UInt8, at point: CGPoint) {
        var data = Data([2, phase.rawValue, id])
        for value in [Float(point.x), Float(point.y)] {
            withUnsafeBytes(of: value.bitPattern.bigEndian) { data.append(contentsOf: $0) }
        }
        queue.async { self.connection?.send(content: data, completion: .idempotent) }
    }

    private func show(status: String) {
        DispatchQueue.main.async { self.status = status }
    }
}

/// This device's IPv4 addresses on Wi-Fi or Personal Hotspot, for typing into `sender.py --host`.
func localAddresses() -> [String] {
    var result: [String] = []
    var ifaddr: UnsafeMutablePointer<ifaddrs>?
    guard getifaddrs(&ifaddr) == 0, let first = ifaddr else { return [] }
    defer { freeifaddrs(ifaddr) }
    for ptr in sequence(first: first, next: { $0.pointee.ifa_next }) {
        guard let addr = ptr.pointee.ifa_addr, addr.pointee.sa_family == UInt8(AF_INET) else { continue }
        let name = String(cString: ptr.pointee.ifa_name)
        guard name.hasPrefix("en") || name.hasPrefix("bridge") else { continue }
        var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
        if getnameinfo(addr, socklen_t(addr.pointee.sa_len), &host, socklen_t(host.count),
                       nil, 0, NI_NUMERICHOST) == 0 {
            result.append(String(cString: host))
        }
    }
    return result
}
