/* One PS-supplied K4 case per CPU reset. Expected values never enter the CPU.
 * Input is package_mlkem.pack_fixture([case], 1024, False), with local index 0.
 * KATP commits the output transport; the PS must compare bytes and API return.
 * Cycle measurement includes only the API call, as in kat_suite/board_kat.
 */
#include <stdint.h>
#include "mlkem_native.h"
#include "kat_protocol.h"

#define CAT_(a, b) a##b
#define CAT(a, b) CAT_(a, b)
#define API(name) CAT(MLK_CONFIG_NAMESPACE_PREFIX, CAT(_, name))
#define PK_BYTES MLKEM_PUBLICKEYBYTES(MLK_CONFIG_PARAMETER_SET)
#define SK_BYTES MLKEM_SECRETKEYBYTES(MLK_CONFIG_PARAMETER_SET)
#define CT_BYTES MLKEM_CIPHERTEXTBYTES(MLK_CONFIG_PARAMETER_SET)
#define MAX2(a, b) ((a) > (b) ? (a) : (b))

/* Linker-owned NOLOAD windows are outside the startup BSS clearing range. */
extern volatile uint32_t __ps_input_start[], __ps_output_start[];
#define WINDOW_BYTES 8192u
#define WINDOW_WORDS (WINDOW_BYTES / 4u)
#define INPUT_HEADER_WORDS 8u
#define META_WORDS 12u
#define OUTPUT_HEADER_WORDS 8u
#define INPUT_MAGIC UINT32_C(0x3254414b)
#define OUTPUT_MAGIC UINT32_C(0x4b34524f)

/* Stable KAT_DEBUG_ERROR values. These report protocol errors, not API returns. */
enum {
    ERR_INPUT_BOUNDS = 1,
    ERR_MAGIC = 2,
    ERR_ABI = 3,
    ERR_PARAMETER = 4,
    ERR_CASE_COUNT = 5,
    ERR_TOTAL_WORDS = 6,
    ERR_HEADER_RESERVED = 7,
    ERR_CASE_INDEX = 8,
    ERR_DATASET = 9,
    ERR_IDENTIFIERS = 10,
    ERR_META_RESERVED = 11,
    ERR_OPERATION = 12,
    ERR_INPUT_LENGTHS = 13,
    ERR_OUTPUT_LENGTHS = 14,
    ERR_SHAPE = 15,
    ERR_PAYLOAD_TOTAL = 16,
    ERR_TRAILING_INPUT = 17
};

static uint8_t input1[SK_BYTES], input2[SK_BYTES], input3[CT_BYTES];
static uint8_t output1[MAX2(PK_BYTES, CT_BYTES)], output2[SK_BYTES], coins[64];
static uint32_t cursor, input_words;

static void fail(uint32_t code)
{
    KAT_DEBUG_ERROR = code;
    __asm__ volatile ("fence iorw, iorw" : : : "memory");
    KAT_DEBUG_STATUS = KAT_STATUS_FAIL;
    KAT_DEBUG_EVENT = KAT_EVENT_DONE;
    for (;;) __asm__ volatile ("nop");
}

static uint32_t receive_word(void)
{
    if (cursor >= input_words || cursor >= WINDOW_WORDS) fail(ERR_INPUT_BOUNDS);
    return __ps_input_start[cursor++];
}

static void receive_bytes(uint8_t *buffer, uint32_t size)
{
    for (uint32_t i = 0; i < size; i += 4) {
        uint32_t word = receive_word();
        for (uint32_t b = 0; b < 4; ++b) buffer[i + b] = (uint8_t)(word >> (8 * b));
    }
}

static uint32_t store_bytes(const uint8_t *buffer, uint32_t size, uint32_t offset)
{
    for (uint32_t i = 0; i < size; i += 4)
        __ps_output_start[offset++] = kat_pack_le(buffer + i, 4);
    return offset;
}

static uint32_t empty_bracket(void)
{
    uint32_t start, stop;
    __asm__ volatile ("rdcycle %0\n\trdcycle %1" : "=&r"(start), "=r"(stop) : : "memory");
    return stop - start;
}

void kat_main(void)
{
    uint32_t header[INPUT_HEADER_WORDS], meta[META_WORDS];
    uint32_t start, stop, offset, empty;
    int result;
    KAT_DEBUG_STATUS = KAT_STATUS_RUN;
    KAT_DEBUG_ERROR = 0;
    __ps_output_start[0] = 0; /* An invalid request cannot expose a stale result. */
    empty = empty_bracket();
    KAT_DEBUG_AUX4 = empty;
    input_words = WINDOW_WORDS;
    for (uint32_t i = 0; i < INPUT_HEADER_WORDS; ++i) header[i] = receive_word();
    if (header[0] != INPUT_MAGIC) fail(ERR_MAGIC);
    if (header[1] != 1) fail(ERR_ABI);
    if (header[2] != MLK_CONFIG_PARAMETER_SET) fail(ERR_PARAMETER);
    if (header[3] != 1) fail(ERR_CASE_COUNT);
    if (header[4] < INPUT_HEADER_WORDS + META_WORDS || header[4] > WINDOW_WORDS)
        fail(ERR_TOTAL_WORDS);
    if (header[5] || header[6] || header[7]) fail(ERR_HEADER_RESERVED);
    input_words = header[4];
    for (uint32_t i = 0; i < META_WORDS; ++i) meta[i] = receive_word();
    if (meta[0] != 0) fail(ERR_CASE_INDEX);
    if (meta[1] < 1 || meta[1] > 3) fail(ERR_DATASET);
    if (!meta[2] || !meta[3] || !meta[4]) fail(ERR_IDENTIFIERS);
    if (meta[11]) fail(ERR_META_RESERVED);
    uint32_t op = meta[5], n1 = meta[6], n2 = meta[7], n3 = meta[8];
    uint32_t o1 = meta[9], o2 = meta[10];
    if (op < 1 || op > 6) fail(ERR_OPERATION);
    if (((n1 | n2 | n3) & 3u) || n1 > sizeof(input1) ||
        n2 > sizeof(input2) || n3 > sizeof(input3)) fail(ERR_INPUT_LENGTHS);
    if (((o1 | o2) & 3u) || o1 > sizeof(output1) || o2 > sizeof(output2) ||
        o1 + o2 > WINDOW_BYTES - 4u * OUTPUT_HEADER_WORDS) fail(ERR_OUTPUT_LENGTHS);
    int shape =
        (op == 1 && n1 == 32 && n2 == 32 && n3 == 0 && o1 == PK_BYTES && o2 == SK_BYTES) ||
        (op == 2 && n1 == PK_BYTES && n2 == 32 && n3 == 0 && o1 == CT_BYTES && o2 == 32) ||
        (op == 3 && n1 == SK_BYTES && n2 == CT_BYTES && n3 == 0 && o1 == 32 && o2 == 0) ||
        (op == 4 && n1 == 32 && n2 == 32 && n3 == CT_BYTES && o1 == 32 && o2 == 0) ||
        (op == 5 && n1 == PK_BYTES && n2 == 0 && n3 == 0 && o1 == 0 && o2 == 0) ||
        (op == 6 && n1 == SK_BYTES && n2 == 0 && n3 == 0 && o1 == 0 && o2 == 0);
    if (!shape) fail(ERR_SHAPE);
    if (INPUT_HEADER_WORDS + META_WORDS + (n1 + n2 + n3) / 4u != input_words)
        fail(ERR_PAYLOAD_TOTAL);
    receive_bytes(input1, n1); receive_bytes(input2, n2); receive_bytes(input3, n3);
    if (cursor != input_words) fail(ERR_TRAILING_INPUT);
    for (uint32_t i = 0; i < sizeof(output1); ++i) output1[i] = 0xa5;
    for (uint32_t i = 0; i < sizeof(output2); ++i) output2[i] = 0xa5;
    if (op == 1 || op == 4)
        for (uint32_t i = 0; i < 32; ++i) { coins[i] = input1[i]; coins[32 + i] = input2[i]; }

    KAT_DEBUG_CASE = 0; KAT_DEBUG_CYCLES = 0; KAT_DEBUG_AUX0 = op;
    KAT_DEBUG_AUX1 = meta[1]; KAT_DEBUG_AUX2 = meta[4];
    KAT_DEBUG_AUX3 = n1 + n2 + n3; KAT_DEBUG_AUX5 = 0;
    kat_emit(KAT_EVENT_CASE_BEGIN, 0, (const uint8_t *)0, 0);
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

    /* Header: magic, ABI, operation, int32 API return, two byte counts,
     * raw cycles, empty-bracket cycles. Payload is out1 || out2, little endian.
     * The completion marker follows all shared-RAM stores and a store barrier.
     */
    offset = store_bytes(output1, o1, OUTPUT_HEADER_WORDS);
    store_bytes(output2, o2, offset);
    __ps_output_start[1] = 1;
    __ps_output_start[2] = op;
    __ps_output_start[3] = (uint32_t)result;
    __ps_output_start[4] = o1;
    __ps_output_start[5] = o2;
    __ps_output_start[6] = stop - start;
    __ps_output_start[7] = empty;
    __ps_output_start[0] = OUTPUT_MAGIC;
    kat_emit(KAT_EVENT_CASE_END, 0, (const uint8_t *)0, 0);
    __asm__ volatile ("fence iorw, iorw" : : : "memory");
    KAT_DEBUG_STATUS = KAT_STATUS_PASS; KAT_DEBUG_EVENT = KAT_EVENT_DONE;
    for (;;) __asm__ volatile ("nop");
}
