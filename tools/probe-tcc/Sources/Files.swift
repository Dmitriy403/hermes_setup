import Foundation
import Darwin

// Per-path Files & Folders probe. Attempts to readdir the path; EPERM
// means TCC has denied access, ENOENT means the path doesn't exist,
// success means access is permitted.
func probeFiles(paths: [String], selfTest: Bool) -> [FilesEntry] {
    let method = "readdir"
    var results: [FilesEntry] = []

    for raw in paths {
        let expanded = (raw as NSString).expandingTildeInPath
        var entry = FilesEntry(
            path: raw,
            status: .unknown,
            method: method,
            errno_name: nil,
            required_sandbox_rules: nil
        )

        let dir = opendir(expanded)
        if dir != nil {
            closedir(dir)
            entry = FilesEntry(
                path: raw,
                status: .granted,
                method: method,
                errno_name: nil,
                required_sandbox_rules: nil
            )
        } else {
            let err = errno
            let errName: String
            switch err {
            case EPERM: errName = "EPERM"
            case EACCES: errName = "EACCES"
            case ENOENT: errName = "ENOENT"
            default:    errName = "errno=\(err)"
            }
            if selfTest && (err == EPERM || err == EACCES) {
                entry = FilesEntry(
                    path: raw,
                    status: .blocked_by_sandbox,
                    method: method,
                    errno_name: errName,
                    required_sandbox_rules: SandboxRules.filesPath(expanded)
                )
            } else if err == ENOENT {
                // Treat absent paths as denied (nothing to read).
                entry = FilesEntry(
                    path: raw,
                    status: .denied,
                    method: method,
                    errno_name: errName,
                    required_sandbox_rules: nil
                )
            } else {
                entry = FilesEntry(
                    path: raw,
                    status: .denied,
                    method: method,
                    errno_name: errName,
                    required_sandbox_rules: nil
                )
            }
        }
        results.append(entry)
    }
    return results
}
