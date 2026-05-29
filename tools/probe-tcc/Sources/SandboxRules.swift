import Foundation

// Per-category Seatbelt allow rules — emitted as `required_sandbox_rules`
// when a probe is suppressed by an active sandbox profile.
//
// NOTE: For v1 these constants are hard-coded in Swift. Task 17.1 will
// move them to `tools/probe-tcc/sandbox-rules.yaml` so the install-time
// profile generator (Python) and this probe share a single source of
// truth. When that lands, regenerate this file or embed the YAML.

enum SandboxRules {
    static let screenRecording: [String] = [
        "(allow mach-lookup (global-name \"com.apple.windowserver.active\"))",
        "(allow mach-lookup (global-name \"com.apple.tccd\"))",
    ]

    static let accessibility: [String] = [
        "(allow mach-lookup (global-name \"com.apple.accessibility.api\"))",
        "(allow mach-lookup (global-name \"com.apple.tccd\"))",
    ]

    static let automationBase: [String] = [
        "(allow mach-lookup (global-name \"com.apple.coreservices.appleevents\"))",
    ]

    static func automationTarget(bundleID: String) -> [String] {
        return [
            "(allow appleevent-send (subpath \"\(bundleID)\"))",
        ]
    }

    static let fullDiskAccess: [String] = [
        "(allow file-read* (literal \"/Library/Application Support/com.apple.TCC/TCC.db\"))",
    ]

    static let microphone: [String] = [
        "(allow mach-lookup (global-name \"com.apple.audio.audiohald\"))",
        "(allow mach-lookup (global-name \"com.apple.tccd\"))",
    ]

    static let camera: [String] = [
        "(allow mach-lookup (global-name \"com.apple.cmio.AppleCameraAssistant\"))",
        "(allow mach-lookup (global-name \"com.apple.tccd\"))",
    ]

    static let inputMonitoring: [String] = [
        "(allow mach-lookup (global-name \"com.apple.iohideventsystem\"))",
    ]

    static func filesPath(_ path: String) -> [String] {
        return [
            "(allow file-read* (subpath \"\(path)\"))",
        ]
    }
}
