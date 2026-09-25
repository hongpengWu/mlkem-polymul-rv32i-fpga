/* Generic deterministic ML-KEM-512 test driver. Expected results stay in TB. */
#include <stdint.h>
#include "mlkem_native.h"
#include "kat_protocol.h"

#define MAIL_DATA (*(volatile uint32_t *)(KAT_DEBUG_BASE + 40u))
#define MAIL_ACK  (*(volatile uint32_t *)(KAT_DEBUG_BASE + 44u))
#define EVENT_REQUEST UINT32_C(0x200)
#define EVENT_INPUT UINT32_C(0x201)
#define EVENT_OUTPUT UINT32_C(0x202)

static uint8_t input1[1632], input2[768], input3[768];
static uint8_t output1[800], output2[1632], coins[64];
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
    KAT_DEBUG_INDEX = cursor;
    KAT_DEBUG_EVENT = EVENT_REQUEST;
    ++cursor;
    while (MAIL_ACK != cursor) {}
    return MAIL_DATA;
}

static void receive_bytes(uint8_t *buffer, uint32_t size)
{
    for (uint32_t i = 0; i < size; i += 4) {
        uint32_t word = receive_word();
        for (uint32_t b = 0; b < 4; ++b)
            buffer[i + b] = (uint8_t)(word >> (8 * b));
    }
}

static uint32_t emit_bytes(uint32_t event, const uint8_t *data,
                           uint32_t size, uint32_t offset)
{
    for (uint32_t i = 0; i < size; i += 4)
        kat_emit(event, offset++, data + i, 4);
    return offset;
}

static uint32_t empty_bracket(void)
{
    uint32_t start, stop;
    __asm__ volatile ("rdcycle %0\n\trdcycle %1"
                      : "=&r"(start), "=r"(stop) : : "memory");
    return stop - start;
}

void kat_main(void)
{
    uint32_t header[8], meta[12];
    KAT_DEBUG_STATUS = KAT_STATUS_RUN;
    KAT_DEBUG_ERROR = 0;
    KAT_DEBUG_AUX4 = empty_bracket();
    for (uint32_t i = 0; i < 8; ++i) header[i] = receive_word();
    if (header[0] != 0x3254414b || header[1] != 1 || header[2] != 512 ||
        header[3] == 0 || header[3] > 145 || header[4] < 8 ||
        header[5] || header[6] || header[7]) fail(1);

    for (uint32_t c = 0; c < header[3]; ++c) {
        uint32_t start, stop, offset;
        int result;
        for (uint32_t i = 0; i < 12; ++i) meta[i] = receive_word();
        if (meta[0] != c || meta[1] < 1 || meta[1] > 3 || meta[11]) fail(2);
        uint32_t op = meta[5], n1 = meta[6], n2 = meta[7], n3 = meta[8];
        uint32_t o1 = meta[9], o2 = meta[10];
        int shape =
            (op == 1 && n1 == 32 && n2 == 32 && n3 == 0 && o1 == 800 && o2 == 1632) ||
            (op == 2 && n1 == 800 && n2 == 32 && n3 == 0 && o1 == 768 && o2 == 32) ||
            (op == 3 && n1 == 1632 && n2 == 768 && n3 == 0 && o1 == 32 && o2 == 0) ||
            (op == 4 && n1 == 32 && n2 == 32 && n3 == 768 && o1 == 32 && o2 == 0) ||
            (op == 5 && n1 == 800 && n2 == 0 && n3 == 0 && o1 == 0 && o2 == 0) ||
            (op == 6 && n1 == 1632 && n2 == 0 && n3 == 0 && o1 == 0 && o2 == 0);
        if (!shape) fail(3);
        receive_bytes(input1, n1);
        receive_bytes(input2, n2);
        receive_bytes(input3, n3);
        for (uint32_t i = 0; i < sizeof(output1); ++i) output1[i] = 0xa5;
        for (uint32_t i = 0; i < sizeof(output2); ++i) output2[i] = 0xa5;
        if (op == 1 || op == 4)
            for (uint32_t i = 0; i < 32; ++i) {
                coins[i] = input1[i]; coins[32 + i] = input2[i];
            }

        KAT_DEBUG_CASE = c;
        KAT_DEBUG_CYCLES = 0;
        KAT_DEBUG_AUX0 = op;
        KAT_DEBUG_AUX1 = meta[1];
        KAT_DEBUG_AUX2 = meta[4];
        KAT_DEBUG_AUX3 = n1 + n2 + n3;
        KAT_DEBUG_AUX5 = 0;
        kat_emit(KAT_EVENT_CASE_BEGIN, 0, (const uint8_t *)0, 0);
        offset = emit_bytes(EVENT_INPUT, input1, n1, 0);
        offset = emit_bytes(EVENT_INPUT, input2, n2, offset);
        emit_bytes(EVENT_INPUT, input3, n3, offset);

        KAT_DEBUG_EVENT = KAT_EVENT_MEASURE_BEGIN;
        start = kat_cycle();
        switch (op) {
        case 1:
            result = pico_mlkem512_keypair_derand(output1, output2, coins);
            break;
        case 2:
            result = pico_mlkem512_enc_derand(output1, output2, input1, input2);
            break;
        case 3:
            result = pico_mlkem512_dec(output1, input2, input1);
            break;
        case 4:
            /* Seed-form decapsulation includes key expansion in this window. */
            result = pico_mlkem512_keypair_derand(output1, output2, coins);
            if (result == 0) result = pico_mlkem512_dec(output1, input3, output2);
            break;
        case 5:
            result = pico_mlkem512_check_pk(input1);
            break;
        default: /* op == 6, validated before receiving inputs. */
            result = pico_mlkem512_check_sk(input1);
            break;
        }
        stop = kat_cycle();
        KAT_DEBUG_EVENT = KAT_EVENT_MEASURE_END;
        KAT_DEBUG_CYCLES = stop - start;
        KAT_DEBUG_AUX5 = (uint32_t)result;
        offset = emit_bytes(EVENT_OUTPUT, output1, o1, 0);
        emit_bytes(EVENT_OUTPUT, output2, o2, offset);
        kat_emit(KAT_EVENT_CASE_END, 0, (const uint8_t *)0, 0);
    }
    if (cursor != header[4]) fail(4);
    KAT_DEBUG_STATUS = KAT_STATUS_PASS;
    KAT_DEBUG_EVENT = KAT_EVENT_DONE;
    for (;;) __asm__ volatile ("nop");
}
