import Foundation
import Darwin

// MARK: - Low-level process info via sysctl

private func kinfo(pid: pid_t) -> kinfo_proc? {
    var info = kinfo_proc()
    var size = MemoryLayout<kinfo_proc>.size
    var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_PID, pid]
    let result = mib.withUnsafeMutableBufferPointer { mibPtr -> Int32 in
        sysctl(mibPtr.baseAddress, UInt32(mibPtr.count), &info, &size, nil, 0)
    }
    guard result == 0, size > 0 else { return nil }
    return info
}

private func parentPid(of pid: pid_t) -> pid_t? {
    guard let info = kinfo(pid: pid) else { return nil }
    return info.kp_eproc.e_ppid
}

private func processName(of pid: pid_t) -> String {
    guard var info = kinfo(pid: pid) else { return "?" }
    let size = MemoryLayout.size(ofValue: info.kp_proc.p_comm)
    return withUnsafePointer(to: &info.kp_proc.p_comm) { ptr in
        ptr.withMemoryRebound(to: CChar.self, capacity: size) {
            String(cString: $0)
        }
    }
}

// KERN_PROCARGS2 returns: [argc:int32][exe_path:cstring][argv0:cstring]...
// We pull just the exe_path. May fail with EPERM for processes we
// don't own (e.g., launchd) — caller treats nil as "unknown".
private func executablePath(of pid: pid_t) -> String? {
    var mib: [Int32] = [CTL_KERN, KERN_PROCARGS2, pid]
    var size: Int = 0
    let probeStatus = mib.withUnsafeMutableBufferPointer { mibPtr -> Int32 in
        sysctl(mibPtr.baseAddress, UInt32(mibPtr.count), nil, &size, nil, 0)
    }
    guard probeStatus == 0, size > 0 else { return nil }

    var buf = [CChar](repeating: 0, count: size)
    let readStatus = mib.withUnsafeMutableBufferPointer { mibPtr -> Int32 in
        sysctl(mibPtr.baseAddress, UInt32(mibPtr.count), &buf, &size, nil, 0)
    }
    guard readStatus == 0 else { return nil }

    return buf.withUnsafeBufferPointer { (bp: UnsafeBufferPointer<CChar>) -> String? in
        guard let base = bp.baseAddress else { return nil }
        // Skip the leading argc (int32, 4 bytes).
        let exePtr = base.advanced(by: MemoryLayout<Int32>.size)
        return String(cString: exePtr)
    }
}

private func bundleID(forAppExecutable path: String) -> String? {
    // Walk from /Apps/Foo.app/Contents/MacOS/foo back up to .../Foo.app
    // and read its Info.plist.
    guard let appRange = path.range(of: ".app/", options: .backwards) else { return nil }
    let appPath = String(path[..<appRange.upperBound]).dropLast()  // strip trailing "/"
    let url = URL(fileURLWithPath: String(appPath))
    return Bundle(url: url)?.bundleIdentifier
}

// MARK: - Public API

func detectResponsibleProcess() -> ResponsibleInfo {
    var entries: [ChainEntry] = []
    var currentPid = getpid()
    var responsiblePid: pid_t? = nil
    var responsiblePath: String? = nil
    var responsibleBundleID: String? = nil
    var responsibleName: String? = nil

    // Walk up to 50 ancestors as a safety cap.
    for _ in 0..<50 {
        let path = executablePath(of: currentPid)
        let name = processName(of: currentPid)
        var bid: String? = nil
        if let p = path, p.contains(".app/Contents/MacOS/") {
            bid = bundleID(forAppExecutable: p)
        }
        var entry = ChainEntry(pid: currentPid, name: name, path: path, bundle_id: bid, is_responsible: nil)

        if responsiblePid == nil, let p = path, p.contains(".app/Contents/MacOS/") {
            responsiblePid = currentPid
            responsiblePath = p
            responsibleBundleID = bid
            responsibleName = name
            entry.is_responsible = true
        }
        entries.append(entry)

        guard let next = parentPid(of: currentPid), next > 1, next != currentPid else { break }
        currentPid = next
    }

    if responsiblePid == nil {
        let top = entries.last
        return ResponsibleInfo(
            pid: top?.pid ?? -1,
            path: top?.path,
            bundle_id: nil,
            name: top?.name ?? "?",
            chain: entries,
            is_responsible_unknown: true
        )
    }

    return ResponsibleInfo(
        pid: responsiblePid!,
        path: responsiblePath,
        bundle_id: responsibleBundleID,
        name: responsibleName ?? "?",
        chain: entries,
        is_responsible_unknown: nil
    )
}

// MARK: - Sandbox detection

func detectSandbox(chain: [ChainEntry], selfTest: Bool) -> SandboxInfo {
    // `sandbox-exec` exec()s the child directly, so the ancestor chain
    // does NOT contain a `sandbox-exec` entry and it also sets no
    // distinguishing environment variable. The reliable signal is the
    // caller's explicit `--self-test` flag, which doctor only uses when
    // launching the probe through `sandbox-exec -f <profile>`.
    if selfTest {
        let profilePath = ProcessInfo.processInfo.environment["HERMES_SANDBOX_PROFILE"]
        return SandboxInfo(active: true, profile_path: profilePath)
    }
    // Defensive fallbacks for direct (non-doctor) invocations.
    if let profile = ProcessInfo.processInfo.environment["SANDBOX_PROFILE"], !profile.isEmpty {
        return SandboxInfo(active: true, profile_path: profile)
    }
    for entry in chain {
        if entry.name == "sandbox-exec" {
            return SandboxInfo(active: true, profile_path: nil)
        }
    }
    return SandboxInfo(active: false, profile_path: nil)
}
