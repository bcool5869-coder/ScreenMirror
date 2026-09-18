import SwiftUI

struct ContentView: View {
    @ObservedObject var server: FrameServer

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if let frame = server.frame {
                Image(uiImage: frame)
                    .resizable()
                    .interpolation(.medium)
                    .aspectRatio(contentMode: .fit)
                    .ignoresSafeArea()
                TouchLayer(imageSize: frame.size) { phase, id, point in
                    server.sendFinger(phase, id: id, at: point)
                }
                .ignoresSafeArea()
            } else {
                waiting
            }
        }
        .statusBarHidden(true)
        .persistentSystemOverlays(.hidden)
        .defersSystemGestures(on: .all)  // edge swipes go to the PC first, not iOS
    }

    private var waiting: some View {
        VStack(spacing: 14) {
            Image(systemName: "display")
                .font(.system(size: 48))
            Text("ScreenMirror")
                .font(.title2.bold())
            Text(server.status)
                .foregroundStyle(.gray)
            let addresses = localAddresses()
            Text(addresses.isEmpty ? "Cable: plug in and run sender.py on the PC"
                                   : "Wi-Fi address: \(addresses.joined(separator: ", "))  ·  port 7700")
                .font(.footnote.monospaced())
                .foregroundStyle(.gray)
        }
        .foregroundStyle(.white)
        .padding()
    }
}
