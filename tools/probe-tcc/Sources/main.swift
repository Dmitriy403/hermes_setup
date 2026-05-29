import Foundation

// MARK: - CLI argument parsing

struct Args {
    var json: Bool = false
    var selfTest: Bool = false
    var automationTargets: [String] = []
    var expectFiles: [String] = ["~/Documents", "~/Desktop", "~/Downloads"]
    var showHelp: Bool = false
}

func parseArgs(_ argv: [String]) -> Args {
    var args = Args()
    for raw in argv.dropFirst() {
        switch raw {
        case "--json":
            args.json = true
        case "--self-test":
            args.selfTest = true
        case "--help", "-h":
            args.showHelp = true
        default:
            if raw.hasPrefix("--automation-targets=") {
                let v = String(raw.dropFirst("--automation-targets=".count))
                args.automationTargets = v.split(separator: ",").map { String($0) }
            } else if raw.hasPrefix("--expect-files=") {
                let v = String(raw.dropFirst("--expect-files=".count))
                args.expectFiles = v.split(separator: ",").map { String($0) }
            }
        }
    }
    return args
}

func printHelp() {
    let usage = """
    hermes-probe-tcc — silent macOS TCC permission probe

    USAGE:
        hermes-probe-tcc [OPTIONS]

    OPTIONS:
        --json                              Emit JSON v1 (default: human format)
        --self-test                         Map plausible Seatbelt errors to
                                            status=blocked_by_sandbox. Intended
                                            for use under `sandbox-exec -f ...`.
        --automation-targets=BUNDLE,BUNDLE  Comma-separated bundle ids to probe
                                            for Automation (AppleEvents) access.
        --expect-files=PATH,PATH            Comma-separated absolute or tilde
                                            paths to probe for Files & Folders
                                            access.
                                            (default: ~/Documents,~/Desktop,~/Downloads)
        -h, --help                          Show this help

    EXIT CODES:
        0  all probed categories granted
        2  at least one denied
        See specs/doctor for the full classification taken by `hermes doctor`.

    Schema URI: https://hermes/probe-tcc/v1
    """
    FileHandle.standardError.write(Data((usage + "\n").utf8))
}

// MARK: - Aggregate result

func computeSummary(probes: Probes) -> Summary {
    var total = 0
    var granted = 0
    var denied = 0
    var partial = 0
    var blocked = 0

    func tally(_ s: ProbeStatus) {
        total += 1
        switch s {
        case .granted: granted += 1
        case .denied: denied += 1
        case .partial: partial += 1
        case .blocked_by_sandbox: blocked += 1
        default: break
        }
    }
    tally(probes.screen_recording.status)
    tally(probes.accessibility.status)
    tally(probes.automation.status)
    tally(probes.full_disk_access.status)
    tally(probes.microphone.status)
    tally(probes.camera.status)
    tally(probes.input_monitoring.status)
    for f in probes.files { tally(f.status) }

    return Summary(
        total: total,
        granted: granted,
        denied: denied,
        partial: partial,
        blocked_by_sandbox: blocked
    )
}

func computeExitCode(summary: Summary) -> Int32 {
    if summary.blocked_by_sandbox > 0 { return 3 }
    if summary.denied > 0 || summary.partial > 0 { return 2 }
    return 0
}

// MARK: - Human-readable output

func formatHuman(_ r: ProbeResult) -> String {
    var lines: [String] = []
    lines.append("Hermes TCC probe v\(r.probe_version)")
    lines.append("  Probed at:           \(r.probed_at)")
    lines.append("  cdhash:              \(r.self_info.cdhash ?? "<unknown>")")
    lines.append("  Responsible process: \(r.responsible_process.name) (bundle: \(r.responsible_process.bundle_id ?? "<none>"))")
    if r.sandbox.active {
        lines.append("  Sandbox:             ACTIVE (\(r.sandbox.profile_path ?? "unknown profile"))")
    }
    lines.append("")
    lines.append("CATEGORIES:")
    lines.append("  Screen Recording   \(r.probes.screen_recording.status.rawValue)")
    lines.append("  Accessibility      \(r.probes.accessibility.status.rawValue)")
    lines.append("  Automation         \(r.probes.automation.status.rawValue)")
    for t in r.probes.automation.targets {
        lines.append("    └─ \(t.bundle_id)  \(t.status.rawValue)")
    }
    lines.append("  Full Disk Access   \(r.probes.full_disk_access.status.rawValue)")
    lines.append("  Microphone         \(r.probes.microphone.status.rawValue)")
    lines.append("  Camera             \(r.probes.camera.status.rawValue)")
    lines.append("  Input Monitoring   \(r.probes.input_monitoring.status.rawValue)")
    lines.append("  Files:")
    for f in r.probes.files {
        lines.append("    \(f.path.padding(toLength: 22, withPad: " ", startingAt: 0))  \(f.status.rawValue)")
    }
    lines.append("")
    lines.append("SUMMARY: \(r.summary.granted) granted / \(r.summary.denied) denied / \(r.summary.blocked_by_sandbox) blocked-by-sandbox / \(r.summary.partial) partial  (total \(r.summary.total))")
    return lines.joined(separator: "\n")
}

// MARK: - Main entry

let args = parseArgs(CommandLine.arguments)

if args.showHelp {
    printHelp()
    exit(0)
}

let responsible = detectResponsibleProcess()
let sandbox = detectSandbox(chain: responsible.chain, selfTest: args.selfTest)

let probes = Probes(
    screen_recording: probeScreenRecording(selfTest: args.selfTest),
    accessibility: probeAccessibility(selfTest: args.selfTest),
    automation: probeAutomation(targets: args.automationTargets, selfTest: args.selfTest),
    full_disk_access: probeFullDiskAccess(selfTest: args.selfTest),
    microphone: probeMicrophone(selfTest: args.selfTest),
    camera: probeCamera(selfTest: args.selfTest),
    input_monitoring: probeInputMonitoring(selfTest: args.selfTest),
    files: probeFiles(paths: args.expectFiles, selfTest: args.selfTest)
)

let summary = computeSummary(probes: probes)
let exitCode = computeExitCode(summary: summary)

let selfInfo = SelfInfo(
    bundle_id: selfBundleID(),
    binary_path: selfBinaryPath(),
    cdhash: readSelfCdhash(),
    signature: "ad-hoc"  // v1 Scenario A; revisit if migrating to Developer ID
)

let result = ProbeResult(
    schema: "https://hermes/probe-tcc/v1",
    probe_version: "0.1.0",
    probed_at: currentISO8601(),
    self_info: selfInfo,
    responsible_process: responsible,
    sandbox: sandbox,
    probes: probes,
    summary: summary,
    exit_code: exitCode
)

if args.json {
    print(JSON.encode(result))
} else {
    print(formatHuman(result))
}

exit(exitCode)
