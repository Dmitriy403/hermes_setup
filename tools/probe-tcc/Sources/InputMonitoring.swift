import Foundation
import IOKit.hid

// IOHIDCheckAccess returns IOHIDAccessType:
//   .granted, .denied, .unknown (0, 1, 2)
func probeInputMonitoring(selfTest: Bool) -> SimpleProbe {
    let method = "IOHIDCheckAccess(listenEvent)"
    let status = IOHIDCheckAccess(kIOHIDRequestTypeListenEvent)

    switch status {
    case kIOHIDAccessTypeGranted:
        return SimpleProbe(status: .granted, method: method, detail: nil, required_sandbox_rules: nil)
    case kIOHIDAccessTypeDenied:
        if selfTest {
            return SimpleProbe(
                status: .blocked_by_sandbox,
                method: method,
                detail: "denied",
                required_sandbox_rules: SandboxRules.inputMonitoring
            )
        }
        return SimpleProbe(status: .denied, method: method, detail: "denied", required_sandbox_rules: nil)
    case kIOHIDAccessTypeUnknown:
        return SimpleProbe(status: .unknown, method: method, detail: "unknown", required_sandbox_rules: nil)
    default:
        return SimpleProbe(status: .unknown, method: method, detail: "raw=\(status.rawValue)", required_sandbox_rules: nil)
    }
}
