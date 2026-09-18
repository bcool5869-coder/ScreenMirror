import SwiftUI

@main
struct ScreenMirrorApp: App {
    @StateObject private var server = FrameServer()

    var body: some Scene {
        WindowGroup {
            ContentView(server: server)
                .onAppear {
                    UIApplication.shared.isIdleTimerDisabled = true  // it's a monitor; don't sleep
                    server.start()
                }
        }
    }
}
