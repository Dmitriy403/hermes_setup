import Foundation

// MARK: - JSON contract types (schema: https://hermes/probe-tcc/v1)

enum ProbeStatus: String, Codable {
    case granted
    case denied
    case partial
    case blocked_by_sandbox
    case app_not_running
    case not_determined
    case unknown
}

struct SelfInfo: Codable {
    let bundle_id: String
    let binary_path: String
    let cdhash: String?
    let signature: String  // "ad-hoc" for v1, "developer-id" later
}

struct ChainEntry: Codable {
    let pid: Int32
    let name: String
    let path: String?
    var bundle_id: String?
    var is_responsible: Bool?
}

struct ResponsibleInfo: Codable {
    let pid: Int32
    let path: String?
    let bundle_id: String?
    let name: String
    let chain: [ChainEntry]
    var is_responsible_unknown: Bool?
}

struct SandboxInfo: Codable {
    let active: Bool
    let profile_path: String?
}

struct SimpleProbe: Codable {
    let status: ProbeStatus
    let method: String
    var detail: String?
    var required_sandbox_rules: [String]?
}

struct AutomationTarget: Codable {
    let bundle_id: String
    let status: ProbeStatus
    var ae_error: Int32?
    var required_sandbox_rules: [String]?
}

struct AutomationProbe: Codable {
    let status: ProbeStatus
    let method: String
    let targets: [AutomationTarget]
    var required_sandbox_rules: [String]?
}

struct FilesEntry: Codable {
    let path: String
    let status: ProbeStatus
    let method: String
    var errno_name: String?
    var required_sandbox_rules: [String]?
}

struct Probes: Codable {
    let screen_recording: SimpleProbe
    let accessibility: SimpleProbe
    let automation: AutomationProbe
    let full_disk_access: SimpleProbe
    let microphone: SimpleProbe
    let camera: SimpleProbe
    let input_monitoring: SimpleProbe
    let files: [FilesEntry]
}

struct Summary: Codable {
    let total: Int
    let granted: Int
    let denied: Int
    let partial: Int
    let blocked_by_sandbox: Int
}

struct ProbeResult: Codable {
    let schema: String
    let probe_version: String
    let probed_at: String
    let self_info: SelfInfo
    let responsible_process: ResponsibleInfo
    let sandbox: SandboxInfo
    let probes: Probes
    let summary: Summary
    let exit_code: Int32

    enum CodingKeys: String, CodingKey {
        case schema
        case probe_version
        case probed_at
        case self_info = "self"
        case responsible_process
        case sandbox
        case probes
        case summary
        case exit_code
    }
}

// MARK: - JSON encoder helper

enum JSON {
    static func encode<T: Encodable>(_ value: T) -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        do {
            let data = try encoder.encode(value)
            return String(data: data, encoding: .utf8) ?? "{}"
        } catch {
            return "{\"error\":\"\(error)\"}"
        }
    }
}

// MARK: - ISO-8601 timestamp helper

func currentISO8601() -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    return formatter.string(from: Date())
}
