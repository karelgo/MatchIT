import Foundation

extension JSONDecoder.DateDecodingStrategy {
    /// Backend timestamps are Python `datetime.isoformat()`, which emits fractional
    /// seconds only when the microsecond component is non-zero. The stock `.iso8601`
    /// strategy accepts one shape or the other, never both — so try both.
    static var matchITTimestamp: JSONDecoder.DateDecodingStrategy {
        .custom { decoder in
            let text = try decoder.singleValueContainer().decode(String.self)
            if let date = ISO8601DateFormatter.withFractionalSeconds.date(from: text)
                ?? ISO8601DateFormatter.plain.date(from: text)
            {
                return date
            }
            throw DecodingError.dataCorrupted(
                .init(
                    codingPath: decoder.codingPath,
                    debugDescription: "Unrecognised timestamp: \(text)"
                )
            )
        }
    }
}

extension ISO8601DateFormatter {
    // ISO8601DateFormatter is not Sendable, but it is documented as safe to use from
    // multiple threads once configured, and these two are never mutated after creation.
    // Recreating them per decoded value instead would cost more than it buys.
    nonisolated(unsafe) static let withFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    nonisolated(unsafe) static let plain: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}
