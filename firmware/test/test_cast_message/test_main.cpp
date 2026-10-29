// Host tests for the Cast frame codec: `pio test -e native`
#include <unity.h>

#include <string>

#include "cast_message.h"

using castmsg::Message;

void setUp() {}
void tearDown() {}

static Message sample() {
    return Message{"sender-0", "receiver-0", "urn:x-cast:com.google.cast.tp.connection", "{\"type\":\"CONNECT\"}"};
}

static void test_frame_prefix_is_big_endian_body_length() {
    std::string frame = castmsg::encode(sample());
    const uint8_t* h = reinterpret_cast<const uint8_t*>(frame.data());
    TEST_ASSERT_EQUAL_UINT32(frame.size() - 4, castmsg::frameLength(h));
}

static void test_round_trip() {
    Message in = sample();
    std::string body = castmsg::encodeBody(in);
    Message out;
    TEST_ASSERT_TRUE(castmsg::decodeBody(reinterpret_cast<const uint8_t*>(body.data()), body.size(), out));
    TEST_ASSERT_EQUAL_STRING(in.source.c_str(), out.source.c_str());
    TEST_ASSERT_EQUAL_STRING(in.destination.c_str(), out.destination.c_str());
    TEST_ASSERT_EQUAL_STRING(in.ns.c_str(), out.ns.c_str());
    TEST_ASSERT_EQUAL_STRING(in.payload.c_str(), out.payload.c_str());
}

// Bytes produced by the reference implementation (pychromecast / Google protobuf) for the
// same message, so the hand-rolled encoder matches the real wire format byte for byte.
static void test_matches_reference_encoding() {
    const uint8_t expected[] = {
        0x08, 0x00, 0x12, 0x08, 's', 'e', 'n', 'd', 'e', 'r', '-', '0', 0x1a, 0x0a, 'r', 'e', 'c', 'e', 'i', 'v', 'e',
        'r', '-', '0', 0x22, 0x28, 'u', 'r', 'n', ':', 'x', '-', 'c', 'a', 's', 't', ':', 'c', 'o', 'm', '.', 'g', 'o',
        'o', 'g', 'l', 'e', '.', 'c', 'a', 's', 't', '.', 't', 'p', '.', 'c', 'o', 'n', 'n', 'e', 'c', 't', 'i', 'o',
        'n', 0x28, 0x00, 0x32, 0x12, '{', '"', 't', 'y', 'p', 'e', '"', ':', '"', 'C', 'O', 'N', 'N', 'E', 'C', 'T',
        '"', '}'};
    std::string body = castmsg::encodeBody(sample());
    TEST_ASSERT_EQUAL_UINT32(sizeof(expected), body.size());
    TEST_ASSERT_EQUAL_MEMORY(expected, body.data(), sizeof(expected));
}

static void test_long_payload_uses_multibyte_varint() {
    Message m = sample();
    m.payload = std::string(300, 'x');
    std::string body = castmsg::encodeBody(m);
    Message out;
    TEST_ASSERT_TRUE(castmsg::decodeBody(reinterpret_cast<const uint8_t*>(body.data()), body.size(), out));
    TEST_ASSERT_EQUAL_UINT32(300, out.payload.size());
}

static void test_unknown_fields_are_skipped() {
    std::string body = castmsg::encodeBody(sample());
    body.push_back(0x38);  // field 7, varint
    body.push_back(0x05);
    body.push_back(0x3a);  // field 7, length-delimited (binary payload)
    body.push_back(0x02);
    body.append("\x01\x02", 2);
    Message out;
    TEST_ASSERT_TRUE(castmsg::decodeBody(reinterpret_cast<const uint8_t*>(body.data()), body.size(), out));
    TEST_ASSERT_EQUAL_STRING("{\"type\":\"CONNECT\"}", out.payload.c_str());
}

static void test_truncated_body_is_rejected() {
    std::string body = castmsg::encodeBody(sample());
    Message out;
    TEST_ASSERT_FALSE(castmsg::decodeBody(reinterpret_cast<const uint8_t*>(body.data()), body.size() - 3, out));
}

static void test_unsupported_wire_type_is_rejected() {
    const uint8_t bad[] = {0x0d, 0x00, 0x00, 0x00, 0x00};  // field 1, fixed32
    Message out;
    TEST_ASSERT_FALSE(castmsg::decodeBody(bad, sizeof(bad), out));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_frame_prefix_is_big_endian_body_length);
    RUN_TEST(test_round_trip);
    RUN_TEST(test_matches_reference_encoding);
    RUN_TEST(test_long_payload_uses_multibyte_varint);
    RUN_TEST(test_unknown_fields_are_skipped);
    RUN_TEST(test_truncated_body_is_rejected);
    RUN_TEST(test_unsupported_wire_type_is_rejected);
    return UNITY_END();
}
