import Foundation
import Darwin

// FDA probe: attempt to open the system-wide TCC.db read-only. If we can
// read it, the responsible process has FDA. EPERM = not granted.
func probeFullDiskAccess(selfTest: Bool) -> SimpleProbe {
    let path = "/Library/Application Support/com.apple.TCC/TCC.db"
    let method = "open(/Library/.../TCC.db) read-only"
    let fd = open(path, O_RDONLY)

    if fd >= 0 {
        close(fd)
        return SimpleProbe(status: .granted, method: method, detail: nil, required_sandbox_rules: nil)
    }

    let err = errno
    let errName: String
    switch err {
    case EPERM: errName = "EPERM"
    case EACCES: errName = "EACCES"
    case ENOENT: errName = "ENOENT"
    default:    errName = "errno=\(err)"
    }

    if selfTest {
        return SimpleProbe(
            status: .blocked_by_sandbox,
            method: method,
            detail: errName,
            required_sandbox_rules: SandboxRules.fullDiskAccess
        )
    }

    return SimpleProbe(status: .denied, method: method, detail: errName, required_sandbox_rules: nil)
}
