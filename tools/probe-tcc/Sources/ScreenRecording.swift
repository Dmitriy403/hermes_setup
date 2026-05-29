import Foundation
import CoreGraphics

// Silent preflight check for Screen Recording.
// Apple ref: CGPreflightScreenCaptureAccess (macOS 11+).
//
// CGRequestScreenCaptureAccess is the prompting variant and MUST NOT be
// called from --check mode.
func probeScreenRecording(selfTest: Bool) -> SimpleProbe {
    let granted = CGPreflightScreenCaptureAccess()
    let method = "CGPreflightScreenCaptureAccess"

    if granted {
        return SimpleProbe(status: .granted, method: method, detail: nil, required_sandbox_rules: nil)
    }

    if selfTest {
        // Under --self-test we assume any denial is due to the active sandbox
        // profile suppressing the WindowServer mach-lookup before TCC could
        // answer. The doctor compares this to the baseline pass to decide.
        return SimpleProbe(
            status: .blocked_by_sandbox,
            method: method,
            detail: nil,
            required_sandbox_rules: SandboxRules.screenRecording
        )
    }

    return SimpleProbe(status: .denied, method: method, detail: nil, required_sandbox_rules: nil)
}
