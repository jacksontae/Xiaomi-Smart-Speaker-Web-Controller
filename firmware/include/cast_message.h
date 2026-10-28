// Cast v2 wire format: a 4-byte big-endian length, then a protobuf CastMessage.
// Hand-rolled (only six fields are used) so it builds on ESP32, ESP8266 and the host for tests.
//
//   message CastMessage {
//     required ProtocolVersion protocol_version = 1;  // CASTV2_1_0 = 0
//     required string source_id = 2;
//     required string destination_id = 3;
//     required string namespace = 4;
//     required PayloadType payload_type = 5;          // STRING = 0
//     optional string payload_utf8 = 6;
//   }
#pragma once

#include <stddef.h>
#include <stdint.h>

#include <string>

namespace castmsg {

constexpr uint32_t kMaxBody = 64 * 1024;  // receiver status is a few KB; anything larger is junk

struct Message {
    std::string source;
    std::string destination;
    std::string ns;
    std::string payload;
};

inline void putVarint(std::string& out, uint64_t v) {
    while (v >= 0x80) {
        out.push_back(static_cast<char>((v & 0x7F) | 0x80));
        v >>= 7;
    }
    out.push_back(static_cast<char>(v));
}

inline void putString(std::string& out, uint8_t field, const std::string& s) {
    out.push_back(static_cast<char>((field << 3) | 2));
    putVarint(out, s.size());
    out += s;
}

// The protobuf body without the length prefix.
inline std::string encodeBody(const Message& m) {
    std::string body;
    body.push_back(0x08);  // field 1, varint
    body.push_back(0x00);  // CASTV2_1_0
    putString(body, 2, m.source);
    putString(body, 3, m.destination);
    putString(body, 4, m.ns);
    body.push_back(0x28);  // field 5, varint
    body.push_back(0x00);  // STRING
    putString(body, 6, m.payload);
    return body;
}

// A complete frame, ready to write to the socket.
inline std::string encode(const Message& m) {
    std::string body = encodeBody(m);
    uint32_t n = static_cast<uint32_t>(body.size());
    std::string frame;
    frame.reserve(4 + n);
    frame.push_back(static_cast<char>(n >> 24));
    frame.push_back(static_cast<char>(n >> 16));
    frame.push_back(static_cast<char>(n >> 8));
    frame.push_back(static_cast<char>(n));
    return frame + body;
}

inline uint32_t frameLength(const uint8_t header[4]) {
    return (uint32_t(header[0]) << 24) | (uint32_t(header[1]) << 16) | (uint32_t(header[2]) << 8) | header[3];
}

inline bool readVarint(const uint8_t*& p, const uint8_t* end, uint64_t& v) {
    v = 0;
    for (int shift = 0; shift < 64; shift += 7) {
        if (p >= end) return false;
        uint8_t b = *p++;
        v |= uint64_t(b & 0x7F) << shift;
        if (!(b & 0x80)) return true;
    }
    return false;
}

// Decode a protobuf body. Unknown varint and length-delimited fields are skipped;
// binary payloads (payload_type BINARY, field 7) are ignored.
inline bool decodeBody(const uint8_t* data, size_t len, Message& m) {
    const uint8_t* p = data;
    const uint8_t* end = data + len;
    m = Message();
    while (p < end) {
        uint64_t key;
        if (!readVarint(p, end, key)) return false;
        uint32_t field = static_cast<uint32_t>(key >> 3);
        uint8_t wire = key & 7;
        if (wire == 0) {
            uint64_t ignored;
            if (!readVarint(p, end, ignored)) return false;
        } else if (wire == 2) {
            uint64_t n;
            if (!readVarint(p, end, n) || n > static_cast<uint64_t>(end - p)) return false;
            std::string value(reinterpret_cast<const char*>(p), static_cast<size_t>(n));
            p += n;
            switch (field) {
                case 2: m.source = value; break;
                case 3: m.destination = value; break;
                case 4: m.ns = value; break;
                case 6: m.payload = value; break;
                default: break;
            }
        } else {
            return false;  // CastMessage uses no other wire types
        }
    }
    return true;
}

}  // namespace castmsg
