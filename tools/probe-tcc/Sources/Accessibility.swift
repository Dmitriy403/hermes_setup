import Foundation
import ApplicationServices

// Silent check for Accessibility (kAXTrusted) — passes the option
// dictionary with Prompt:false so no dialog is shown.
func probeAccessibility(selfTest: Bool) -> SimpleProbe {
    let promptKey = kAXTrustedCheckOptionPrompt.takeUnretainedValue()
    let options: CFDictionary = [promptKey: false] as CFDictionary
    let trusted = AXIsProcessTrustedWithOptions(options)
    let method = "AXIsProcessTrustedWithOptions"

    if trusted {
        return SimpleProbe(status: .granted, method: method, detail: nil, required_sandbox_rules: nil)
    }

    if selfTest {
        return SimpleProbe(
            status: .blocked_by_sandbox,
            method: method,
            detail: nil,
            required_sandbox_rules: SandboxRules.accessibility
        )
    }

    return SimpleProbe(status: .denied, method: method, detail: nil, required_sandbox_rules: nil)
}
