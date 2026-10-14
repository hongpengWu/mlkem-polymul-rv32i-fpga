/* Standalone board smoke: pinned official K4 KeyGen, Encaps and Decaps.
 * All inputs and answers are compiled into ROM; a host mailbox is unnecessary.
 * The API measurement excludes input copying, stream output and comparisons.
 */
#include <stdint.h>
#include "mlkem_native.h"
#include "kat_protocol.h"
#include "board_vectors.h"

#define EVENT_INPUT UINT32_C(0x201)
#define EVENT_OUTPUT UINT32_C(0x202)
#define CAT_(a, b) a##b
#define CAT(a, b) CAT_(a, b)
#define API(name) CAT(MLK_CONFIG_NAMESPACE_PREFIX, CAT(_, name))
#define PK_BYTES MLKEM_PUBLICKEYBYTES(MLK_CONFIG_PARAMETER_SET)
#define SK_BYTES MLKEM_SECRETKEYBYTES(MLK_CONFIG_PARAMETER_SET)
#define CT_BYTES MLKEM_CIPHERTEXTBYTES(MLK_CONFIG_PARAMETER_SET)
#define MAX2(a, b) ((a) > (b) ? (a) : (b))

static uint8_t input1[SK_BYTES], input2[SK_BYTES], input3[CT_BYTES];
static uint8_t output1[MAX2(PK_BYTES, CT_BYTES)], output2[SK_BYTES], coins[64];
static uint32_t cursor;

static void fail(uint32_t code)
{
    KAT_DEBUG_ERROR = code;
    KAT_DEBUG_STATUS = KAT_STATUS_FAIL;
    KAT_DEBUG_EVENT = KAT_EVENT_DONE;
    for (;;) __asm__ volatile ("nop");
}

static uint32_t receive_word(void)
{
    if (cursor >= BOARD_INPUT_WORDS) fail(1);
    return board_input[cursor++];
}

static void receive_bytes(uint8_t *buffer, uint32_t size)
{
    for (uint32_t i = 0; i < size; i += 4) {
        uint32_t word = receive_word();
        for (uint32_t b = 0; b < 4; ++b) buffer[i + b] = (uint8_t)(word >> (8 * b));
    }
}

static uint32_t emit_bytes(uint32_t event, const uint8_t *data,
                           uint32_t size, uint32_t offset)
{
    for (uint32_t i = 0; i < size; i += 4) kat_emit(event, offset++, data + i, 4);
    return offset;
}

static void check_bytes(const uint8_t *actual, uint32_t size,
                        uint32_t *expected_cursor, uint32_t case_index)
{
    if (*expected_cursor + size / 4 > BOARD_EXPECTED_WORDS) fail(2);
    for (uint32_t i = 0; i < size; ++i) {
        uint32_t word = board_expected[*expected_cursor + i / 4];
        if (actual[i] != (uint8_t)(word >> (8 * (i % 4))))
            fail(UINT32_C(0x10000000) | (case_index << 16) | i);
    }
    *expected_cursor += size / 4;
}

static uint32_t empty_bracket(void)
{
    uint32_t start, stop;
    __asm__ volatile ("rdcycle %0\n\trdcycle %1" : "=&r"(start), "=r"(stop) : : "memory");
    return stop - start;
}

void kat_main(void)
{
    uint32_t header[8], meta[12], expected_cursor = 8;
    KAT_DEBUG_STATUS = KAT_STATUS_RUN;
    KAT_DEBUG_ERROR = 0;
    KAT_DEBUG_AUX4 = empty_bracket();
    for (uint32_t i = 0; i < 8; ++i) header[i] = receive_word();
    if (header[0] != 0x3254414b || header[1] != 1 ||
        header[2] != MLK_CONFIG_PARAMETER_SET || header[3] != BOARD_CASES ||
        header[4] != BOARD_INPUT_WORDS || header[5] || header[6] || header[7]) fail(3);
    for (uint32_t i = 0; i < 8; ++i)
        if (board_expected[i] != (i == 4 ? BOARD_EXPECTED_WORDS : header[i])) fail(4);

    for (uint32_t c = 0; c < header[3]; ++c) {
        uint32_t start, stop, offset;
        int result;
        for (uint32_t i = 0; i < 12; ++i) meta[i] = receive_word();
        if (meta[0] != c || meta[1] < 1 || meta[1] > 3 || meta[11]) fail(5);
        if (expected_cursor + 12 > BOARD_EXPECTED_WORDS) fail(6);
        for (uint32_t i = 0; i < 11; ++i)
            if (meta[i] != board_expected[expected_cursor + i]) fail(7);
        int expected_return = (int32_t)board_expected[expected_cursor + 11];
        expected_cursor += 12;
        uint32_t op = meta[5], n1 = meta[6], n2 = meta[7], n3 = meta[8];
        uint32_t o1 = meta[9], o2 = meta[10];
        int shape =
            (op == 1 && n1 == 32 && n2 == 32 && n3 == 0 && o1 == PK_BYTES && o2 == SK_BYTES) ||
            (op == 2 && n1 == PK_BYTES && n2 == 32 && n3 == 0 && o1 == CT_BYTES && o2 == 32) ||
            (op == 3 && n1 == SK_BYTES && n2 == CT_BYTES && n3 == 0 && o1 == 32 && o2 == 0) ||
            (op == 4 && n1 == 32 && n2 == 32 && n3 == CT_BYTES && o1 == 32 && o2 == 0) ||
            (op == 5 && n1 == PK_BYTES && n2 == 0 && n3 == 0 && o1 == 0 && o2 == 0) ||
            (op == 6 && n1 == SK_BYTES && n2 == 0 && n3 == 0 && o1 == 0 && o2 == 0);
        if (!shape) fail(8);
        receive_bytes(input1, n1); receive_bytes(input2, n2); receive_bytes(input3, n3);
        for (uint32_t i = 0; i < sizeof(output1); ++i) output1[i] = 0xa5;
        for (uint32_t i = 0; i < sizeof(output2); ++i) output2[i] = 0xa5;
        if (op == 1 || op == 4)
            for (uint32_t i = 0; i < 32; ++i) { coins[i] = input1[i]; coins[32 + i] = input2[i]; }

        KAT_DEBUG_CASE = c; KAT_DEBUG_CYCLES = 0; KAT_DEBUG_AUX0 = op;
        KAT_DEBUG_AUX1 = meta[1]; KAT_DEBUG_AUX2 = meta[4]; KAT_DEBUG_AUX3 = n1 + n2 + n3; KAT_DEBUG_AUX5 = 0;
        kat_emit(KAT_EVENT_CASE_BEGIN, 0, (const uint8_t *)0, 0);
        offset = emit_bytes(EVENT_INPUT, input1, n1, 0);
        offset = emit_bytes(EVENT_INPUT, input2, n2, offset);
        emit_bytes(EVENT_INPUT, input3, n3, offset);
        KAT_DEBUG_EVENT = KAT_EVENT_MEASURE_BEGIN; start = kat_cycle();
        switch (op) {
        case 1: result = API(keypair_derand)(output1, output2, coins); break;
        case 2: result = API(enc_derand)(output1, output2, input1, input2); break;
        case 3: result = API(dec)(output1, input2, input1); break;
        case 4:
            result = API(keypair_derand)(output1, output2, coins);
            if (result == 0) result = API(dec)(output1, input3, output2);
            break;
        case 5: result = API(check_pk)(input1); break;
        default: result = API(check_sk)(input1); break;
        }
        stop = kat_cycle(); KAT_DEBUG_EVENT = KAT_EVENT_MEASURE_END;
        KAT_DEBUG_CYCLES = stop - start; KAT_DEBUG_AUX5 = (uint32_t)result;
        offset = emit_bytes(EVENT_OUTPUT, output1, o1, 0); emit_bytes(EVENT_OUTPUT, output2, o2, offset);
        if (result != expected_return) fail(UINT32_C(0x20000000) | c);
        check_bytes(output1, o1, &expected_cursor, c);
        check_bytes(output2, o2, &expected_cursor, c);
        kat_emit(KAT_EVENT_CASE_END, 0, (const uint8_t *)0, 0);
    }
    if (cursor != BOARD_INPUT_WORDS || expected_cursor != BOARD_EXPECTED_WORDS) fail(9);
    KAT_DEBUG_STATUS = KAT_STATUS_PASS; KAT_DEBUG_EVENT = KAT_EVENT_DONE;
    for (;;) __asm__ volatile ("nop");
}
