import Foundation
import CoreServices

// Silent check for Automation permission for each target bundle id.
// Uses AEDeterminePermissionToAutomateTarget with askUserIfNeeded:false.
// Return codes:
//    noErr (0)               → granted
//    errAEEventNotPermitted (-1743) → denied
//    procNotFound (-600)     → app_not_running
//    other                   → unknown
func probeAutomation(targets: [String], selfTest: Bool) -> AutomationProbe {
    let method = "AEDeterminePermissionToAutomateTarget"
    var results: [AutomationTarget] = []
    var grantedCount = 0
    var deniedCount = 0
    var blockedCount = 0

    for bundleID in targets {
        var desc = AEDesc()
        let utf8 = bundleID.utf8CString
        let createStatus = utf8.withUnsafeBufferPointer { buf -> OSStatus in
            // utf8CString includes trailing NUL; pass length without it.
            let length = buf.count - 1
            return OSStatus(AECreateDesc(
                DescType(typeApplicationBundleID),
                buf.baseAddress,
                length,
                &desc
            ))
        }
        guard createStatus == noErr else {
            results.append(AutomationTarget(
                bundle_id: bundleID,
                status: .unknown,
                ae_error: createStatus,
                required_sandbox_rules: nil
            ))
            continue
        }

        let wild = OSType(0x2A2A2A2A)  // '****' — typeWildCard
        let code = AEDeterminePermissionToAutomateTarget(&desc, wild, wild, false)
        AEDisposeDesc(&desc)

        switch code {
        case noErr:
            results.append(AutomationTarget(
                bundle_id: bundleID,
                status: .granted,
                ae_error: 0,
                required_sandbox_rules: nil
            ))
            grantedCount += 1
        case OSStatus(-1743), OSStatus(-1744):
            // -1743 errAEEventNotPermitted — TCC denied.
            // -1744 errAEPrivilegeError    — reachable but not authorized.
            if selfTest {
                var rules = SandboxRules.automationBase
                rules.append(contentsOf: SandboxRules.automationTarget(bundleID: bundleID))
                results.append(AutomationTarget(
                    bundle_id: bundleID,
                    status: .blocked_by_sandbox,
                    ae_error: code,
                    required_sandbox_rules: rules
                ))
                blockedCount += 1
            } else {
                results.append(AutomationTarget(
                    bundle_id: bundleID,
                    status: .denied,
                    ae_error: code,
                    required_sandbox_rules: nil
                ))
                deniedCount += 1
            }
        case OSStatus(-600):  // procNotFound
            results.append(AutomationTarget(
                bundle_id: bundleID,
                status: .app_not_running,
                ae_error: code,
                required_sandbox_rules: nil
            ))
        default:
            results.append(AutomationTarget(
                bundle_id: bundleID,
                status: .unknown,
                ae_error: code,
                required_sandbox_rules: nil
            ))
        }
    }

    // Roll up overall status.
    let overall: ProbeStatus
    if results.isEmpty {
        overall = .granted  // nothing to check
    } else if grantedCount == results.count {
        overall = .granted
    } else if deniedCount == results.count {
        overall = .denied
    } else if blockedCount == results.count {
        overall = .blocked_by_sandbox
    } else {
        overall = .partial
    }

    return AutomationProbe(
        status: overall,
        method: method,
        targets: results,
        required_sandbox_rules: nil  // per-target rules carry the actionable info
    )
}
