import Foundation
import AVFoundation

private func mapStatus(_ s: AVAuthorizationStatus, method: String, selfTest: Bool, rules: [String]) -> SimpleProbe {
    switch s {
    case .authorized:
        return SimpleProbe(status: .granted, method: method, detail: "authorized", required_sandbox_rules: nil)
    case .denied:
        if selfTest {
            return SimpleProbe(status: .blocked_by_sandbox, method: method, detail: "denied", required_sandbox_rules: rules)
        }
        return SimpleProbe(status: .denied, method: method, detail: "denied", required_sandbox_rules: nil)
    case .restricted:
        return SimpleProbe(status: .denied, method: method, detail: "restricted", required_sandbox_rules: nil)
    case .notDetermined:
        return SimpleProbe(status: .not_determined, method: method, detail: "notDetermined", required_sandbox_rules: nil)
    @unknown default:
        return SimpleProbe(status: .unknown, method: method, detail: "unknown", required_sandbox_rules: nil)
    }
}

func probeMicrophone(selfTest: Bool) -> SimpleProbe {
    let s = AVCaptureDevice.authorizationStatus(for: .audio)
    return mapStatus(
        s,
        method: "AVCaptureDevice.authorizationStatus(.audio)",
        selfTest: selfTest,
        rules: SandboxRules.microphone
    )
}

func probeCamera(selfTest: Bool) -> SimpleProbe {
    let s = AVCaptureDevice.authorizationStatus(for: .video)
    return mapStatus(
        s,
        method: "AVCaptureDevice.authorizationStatus(.video)",
        selfTest: selfTest,
        rules: SandboxRules.camera
    )
}
