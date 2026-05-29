import Foundation

// Read this binary's own cdhash. We shell out to `codesign -dv --verbose=4`
// because Security framework's SecCodeCopySigningInformation does not
// reliably expose the cdhash field across SDK versions, and we want the
// exact same hex string the user would see from `codesign --display` so
// `~/.hermes/probe-cache.json` and the doctor stay aligned.
func readSelfCdhash() -> String? {
    let task = Process()
    task.launchPath = "/usr/bin/codesign"
    task.arguments = ["--display", "--verbose=4", selfBinaryPath()]
    let pipe = Pipe()
    task.standardOutput = pipe
    task.standardError = pipe
    do {
        try task.run()
    } catch {
        return nil
    }
    task.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    guard let out = String(data: data, encoding: .utf8) else { return nil }
    for raw in out.components(separatedBy: "\n") {
        let line = raw.trimmingCharacters(in: .whitespaces)
        if line.hasPrefix("CDHash=") {
            return String(line.dropFirst("CDHash=".count))
        }
    }
    return nil
}

// Returns own binary path via /proc/self equivalent (`_NSGetExecutablePath`).
func selfBinaryPath() -> String {
    var size: UInt32 = 4096
    var buf = [CChar](repeating: 0, count: Int(size))
    if _NSGetExecutablePath(&buf, &size) == 0 {
        return String(cString: buf)
    }
    return CommandLine.arguments.first ?? "<unknown>"
}

// Returns the bundle id embedded in our Info.plist section.
func selfBundleID() -> String {
    return Bundle.main.bundleIdentifier ?? "org.hermes.probe-tcc"
}
