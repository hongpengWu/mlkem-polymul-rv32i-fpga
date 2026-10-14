#include "mlkem1024_keccak_accel.h"
#include "generated_keccak_vectors.h"

#include <cstdio>
#include <cstring>

// All expectations originate in Python hashlib, independently of the DUT.
// This is a local FIPS 202 differential/ABI regression, not official K4 KAT.
namespace {

static unsigned transactions = 0;
static unsigned failures = 0;
static const uint64_t CONTEXT_MAGIC = UINT64_C(0x4b344b4300000000);

static unsigned hex_digit(char c) {
    if (c >= '0' && c <= '9') return static_cast<unsigned>(c - '0');
    if (c >= 'a' && c <= 'f') return static_cast<unsigned>(c - 'a' + 10);
    if (c >= 'A' && c <= 'F') return static_cast<unsigned>(c - 'A' + 10);
    return 256;
}

static unsigned hex_byte(const char *hex, unsigned index) {
    return (hex_digit(hex[2 * index]) << 4) | hex_digit(hex[2 * index + 1]);
}

static uint32_t canary(unsigned index) {
    return UINT32_C(0xa5c39e71) ^ (UINT32_C(0x01030507) * index);
}

static bool all_zero(const uint64_t *context) {
    for (unsigned i = 0; i < KECCAK_CONTEXT_WORDS; ++i) {
        if (context[i] != 0) return false;
    }
    return true;
}

static bool metadata_valid(const uint64_t *context, unsigned mode) {
    const uint64_t meta = context[25];
    const unsigned rate = mode == 0 ? 168 : 136;
    return (meta & UINT64_C(0xffffffff00000000)) == CONTEXT_MAGIC &&
           (meta & UINT64_C(0x00000000ff000000)) == 0 &&
           ((meta >> 16) & UINT64_C(0xff)) == mode &&
           (meta & UINT64_C(0xffff)) <= rate;
}

static bool run_transaction(const char *name, const KeccakLocalVector *vector,
                            unsigned input_len, unsigned output_len,
                            unsigned mode, unsigned command,
                            uint64_t context[KECCAK_CONTEXT_WORDS],
                            const char *expected_hex, unsigned expected_offset,
                            int expected_rc, bool context_unchanged = false) {
    uint32_t input[KECCAK_INPUT_WORDS];
    uint32_t original_input[KECCAK_INPUT_WORDS];
    uint32_t output[KECCAK_OUTPUT_WORDS];
    uint64_t original_context[KECCAK_CONTEXT_WORDS];
    for (unsigned i = 0; i < KECCAK_INPUT_WORDS; ++i) input[i] = canary(i + 1000);
    for (unsigned i = 0; i < KECCAK_OUTPUT_WORDS; ++i) output[i] = canary(i);
    std::memcpy(original_context, context, sizeof(original_context));
    if (vector != 0) {
        if (std::strlen(vector->input_hex) != 2u * vector->input_len ||
            vector->input_len > KECCAK_MAX_INPUT_BYTES) {
            std::printf("FAIL fixture_input %s\n", name);
            ++failures;
            return false;
        }
        for (unsigned i = 0; i < vector->input_len; ++i) {
            const unsigned byte = hex_byte(vector->input_hex, i);
            if (byte > 255) {
                std::printf("FAIL fixture_hex %s\n", name);
                ++failures;
                return false;
            }
            const unsigned shift = 8u * (i & 3u);
            input[i / 4] = (input[i / 4] & ~(UINT32_C(0xff) << shift)) |
                           (static_cast<uint32_t>(byte) << shift);
        }
    }
    std::memcpy(original_input, input, sizeof(input));
    ++transactions;
    const int rc = mlkem1024_keccak_accel(input, input_len, output, output_len,
                                         static_cast<uint8_t>(mode),
                                         static_cast<uint8_t>(command), context);
    unsigned errors = 0;
    if (rc != expected_rc) {
        std::printf("FAIL %s rc=%d expected_rc=%d\n", name, rc, expected_rc);
        ++errors;
    }
    if (std::memcmp(input, original_input, sizeof(input)) != 0) {
        std::printf("FAIL %s input_mutated\n", name);
        ++errors;
    }
    if (expected_rc != 0 || command == 2 || output_len == 0) {
        for (unsigned i = 0; i < KECCAK_OUTPUT_WORDS; ++i) {
            if (output[i] != canary(i)) {
                std::printf("FAIL %s output_mutated_at_word=%u\n", name, i);
                ++errors;
                break;
            }
        }
    } else {
        if (expected_hex == 0 ||
            std::strlen(expected_hex) < 2u * (expected_offset + output_len)) {
            std::printf("FAIL fixture_expected %s\n", name);
            ++errors;
        } else {
            for (unsigned i = 0; i < output_len; ++i) {
                const unsigned actual = (output[i / 4] >> (8u * (i & 3u))) & 0xffu;
                const unsigned expected = hex_byte(expected_hex, expected_offset + i);
                if (actual != expected) {
                    std::printf("FAIL %s output_byte=%u actual=%02x expected=%02x\n",
                                name, i, actual, expected);
                    ++errors;
                    break;
                }
            }
        }
        const unsigned written_words = (output_len + 3u) / 4u;
        if ((output_len & 3u) != 0 &&
            (output[written_words - 1] >> (8u * (output_len & 3u))) != 0) {
            std::printf("FAIL %s partial_word_not_zero_padded\n", name);
            ++errors;
        }
        for (unsigned i = written_words; i < KECCAK_OUTPUT_WORDS; ++i) {
            if (output[i] != canary(i)) {
                std::printf("FAIL %s output_tail_mutated_at_word=%u\n", name, i);
                ++errors;
                break;
            }
        }
    }
    if (expected_rc != 0 || context_unchanged) {
        if (std::memcmp(context, original_context, sizeof(original_context)) != 0) {
            std::printf("FAIL %s context_mutated\n", name);
            ++errors;
        }
    } else if (command == 2 || mode >= 2) {
        if (!all_zero(context)) {
            std::printf("FAIL %s context_not_cleared\n", name);
            ++errors;
        }
    } else if (!metadata_valid(context, mode)) {
        std::printf("FAIL %s invalid_context_metadata\n", name);
        ++errors;
    }
    if (errors == 0) {
        std::printf("PASS %03u %s mode=%u command=%u in=%u out=%u rc=%d\n",
                    transactions, name, mode, command, input_len, output_len, rc);
    }
    failures += errors;
    return errors == 0;
}

static void hash_cases(uint64_t valid_shake_context[KECCAK_CONTEXT_WORDS]) {
    // Reuse dirty contexts across successive HASH calls: HASH must initialize,
    // and every one-shot digest must be independent of preceding transactions.
    uint64_t context[KECCAK_CONTEXT_WORDS];
    for (unsigned i = 0; i < KECCAK_CONTEXT_WORDS; ++i) {
        context[i] = UINT64_C(0xcafebabe01230000) + i;
    }
    for (unsigned i = 0; i < HASH_VECTORS_COUNT; ++i) {
        const KeccakLocalVector &v = HASH_VECTORS[i];
        run_transaction(v.name, &v, v.input_len, v.output_len, v.mode, 0,
                        context, v.expected_hex, 0, 0);
        if (i == 0) std::memcpy(valid_shake_context, context, sizeof(context));
    }
}

static void continuation_cases() {
    const unsigned lengths[4] = {13, 0, 491, 168};
    for (unsigned mode = 0; mode < CONTINUATION_VECTORS_COUNT; ++mode) {
        const KeccakLocalVector &v = CONTINUATION_VECTORS[mode];
        uint64_t context[KECCAK_CONTEXT_WORDS] = {};
        unsigned offset = 0;
        for (unsigned part = 0; part < 4; ++part) {
            char name[96];
            std::snprintf(name, sizeof(name), "%s_part%u", v.name, part);
            run_transaction(name, &v, part == 0 ? v.input_len : 0,
                            lengths[part], v.mode, part == 0 ? 0 : 1,
                            context, v.expected_hex, offset, 0, part == 1);
            offset += lengths[part];
        }
    }
}

static void interleaved_cases() {
    uint64_t context_a[KECCAK_CONTEXT_WORDS] = {};
    uint64_t context_b[KECCAK_CONTEXT_WORDS] = {};
    const KeccakLocalVector &a = INTERLEAVED_VECTORS[0];
    const KeccakLocalVector &b = INTERLEAVED_VECTORS[1];
    run_transaction("interleave_A_hash13", &a, a.input_len, 13, a.mode, 0,
                    context_a, a.expected_hex, 0, 0);
    run_transaction("interleave_B_hash0", &b, b.input_len, 0, b.mode, 0,
                    context_b, b.expected_hex, 0, 0);
    run_transaction("interleave_A_squeeze155", &a, 0, 155, a.mode, 1,
                    context_a, a.expected_hex, 13, 0);
    run_transaction("interleave_B_squeeze136", &b, 0, 136, b.mode, 1,
                    context_b, b.expected_hex, 0, 0);
    run_transaction("interleave_A_squeeze169", &a, 0, 169, a.mode, 1,
                    context_a, a.expected_hex, 168, 0);
    run_transaction("interleave_B_squeeze137", &b, 0, 137, b.mode, 1,
                    context_b, b.expected_hex, 136, 0);
}

static void invalid_cases(const uint64_t valid_context[KECCAK_CONTEXT_WORDS]) {
    uint64_t context[KECCAK_CONTEXT_WORDS];
    std::memcpy(context, valid_context, sizeof(context));
    const KeccakLocalVector &v = HASH_VECTORS[0];
    run_transaction("invalid_mode", &v, 0, 32, 255, 0, context, 0, 0, -1);
    run_transaction("invalid_command", &v, 0, 32, 0, 255, context, 0, 0, -1);
    run_transaction("input_too_long", &v, 2049, 32, 0, 0, context, 0, 0, -1);
    run_transaction("output_too_long", &v, 0, 4097, 0, 0, context, 0, 0, -1);
    run_transaction("input_uint32_max", &v, UINT32_C(0xffffffff), 32, 0, 0,
                    context, 0, 0, -1);
    run_transaction("output_uint32_max", &v, 0, UINT32_C(0xffffffff), 0, 0,
                    context, 0, 0, -1);
    run_transaction("sha3_256_wrong_length", &v, 0, 31, 2, 0, context, 0, 0, -1);
    run_transaction("sha3_512_wrong_length", &v, 0, 65, 3, 0, context, 0, 0, -1);
    run_transaction("squeeze_nonzero_input", &v, 1, 32, 0, 1, context, 0, 0, -1);
    run_transaction("squeeze_sha3_mode", &v, 0, 32, 2, 1, context, 0, 0, -1);
    run_transaction("clear_nonzero_input", &v, 1, 0, 0, 2, context, 0, 0, -1);
    run_transaction("clear_nonzero_output", &v, 0, 1, 0, 2, context, 0, 0, -1);

    std::memset(context, 0, sizeof(context));
    run_transaction("squeeze_uninitialized", &v, 0, 32, 0, 1, context, 0, 0, -2);
    std::memcpy(context, valid_context, sizeof(context));
    context[25] ^= UINT64_C(1) << 32;
    run_transaction("squeeze_bad_magic", &v, 0, 32, 0, 1, context, 0, 0, -2);
    std::memcpy(context, valid_context, sizeof(context));
    run_transaction("squeeze_mode_mismatch", &v, 0, 32, 1, 1, context, 0, 0, -2);
    std::memcpy(context, valid_context, sizeof(context));
    context[25] |= UINT64_C(1) << 24;
    run_transaction("squeeze_reserved_metadata", &v, 0, 32, 0, 1,
                    context, 0, 0, -2);
    std::memcpy(context, valid_context, sizeof(context));
    context[25] = (context[25] & ~UINT64_C(0xffff)) | 169;
    run_transaction("squeeze_cursor_over_rate", &v, 0, 32, 0, 1,
                    context, 0, 0, -2);
    std::memcpy(context, valid_context, sizeof(context));
    context[25] = CONTEXT_MAGIC | (UINT64_C(2) << 16);
    run_transaction("squeeze_invalid_stored_mode", &v, 0, 32, 0, 1,
                    context, 0, 0, -2);

    // CLEAR is valid even for malformed state and is repeatable.
    for (unsigned i = 0; i < KECCAK_CONTEXT_WORDS; ++i) {
        context[i] = UINT64_C(0xffffffffffffffff) - i;
    }
    run_transaction("clear_dirty_context", &v, 0, 0, 0, 2, context, 0, 0, 0);
    run_transaction("clear_already_zero", &v, 0, 0, 0, 2, context, 0, 0, 0);
    run_transaction("squeeze_after_clear", &v, 0, 32, 0, 1, context, 0, 0, -2);
}

} // namespace

int main() {
    uint64_t valid_shake_context[KECCAK_CONTEXT_WORDS] = {};
    hash_cases(valid_shake_context);
    continuation_cases();
    interleaved_cases();
    invalid_cases(valid_shake_context);
    const unsigned expected_transactions = 109;
    if (transactions != expected_transactions) {
        std::printf("FAIL transaction_count actual=%u expected=%u\n",
                    transactions, expected_transactions);
        ++failures;
    }
    if (failures != 0) {
        std::printf("MLKEM1024_KECCAK_TB_FAIL transactions=%u errors=%u\n",
                    transactions, failures);
        return 1;
    }
    std::printf("MLKEM1024_KECCAK_TB_PASS transactions=%u hash_vectors=%u "
                "scope=local_hashlib_differential_FIPS202\n",
                transactions, HASH_VECTORS_COUNT);
    return 0;
}
