#include <stdint.h>

#include "poly_ntt.h"
#include "vectors.h"

#define N 256u
#define Q 3329u
#define DEBUG ((volatile uint32_t *)0x50000000u)

static int16_t original_a[N], original_b[N];
static int16_t working_a[N], working_b[N], product[N];

static inline uint32_t cycle(void)
{
    uint32_t value;
    __asm__ volatile ("rdcycle %0" : "=r" (value) : : "memory");
    return value;
}

static uint32_t empty_bracket(void)
{
    uint32_t before, after;
    __asm__ volatile ("rdcycle %0\n\trdcycle %1"
                      : "=&r" (before), "=r" (after) : : "memory");
    return after - before;
}

static void event(uint32_t code)
{
    DEBUG[15] = code;
}

static void generate_inputs(uint32_t test)
{
    uint32_t state = test == 6u ? 0xc0dec0deu : 0x6d6c6b65u;
    uint32_t i;
    for (i = 0; i < N; ++i) {
        uint32_t a = 0, b = 0;
        switch (test) {
        case 0:
            b = i;
            break;
        case 1:
            a = i == 0u;
            b = (17u * i * i + 31u * i + 7u) % Q;
            break;
        case 2:
            a = i == 255u;
            b = i == 1u;
            break;
        case 3:
            a = b = Q - 1u;
            break;
        case 4:
            a = (i & 1u) ? 0u : Q - 1u;
            b = (i & 1u) ? Q - 1u : 1u;
            break;
        case 5:
            a = (17u * i * i + 31u * i + 7u) % Q;
            b = (29u * i * i + 11u * i + 19u) % Q;
            break;
        default:
            state = state * 1664525u + 1013904223u;
            a = state % Q;
            state = state * 1664525u + 1013904223u;
            b = state % Q;
            break;
        }
        original_a[i] = (int16_t)a;
        original_b[i] = (int16_t)b;
    }
}

static void copy_inputs(void)
{
    uint32_t i;
    for (i = 0; i < N; ++i) {
        working_a[i] = original_a[i];
        working_b[i] = original_b[i];
    }
}

static void stream_inputs(void)
{
    uint32_t i;
    for (i = 0; i < N; ++i) {
        DEBUG[12] = i;
        DEBUG[13] = (uint32_t)(uint16_t)original_a[i]
                  | ((uint32_t)(uint16_t)original_b[i] << 16);
        event(2);
    }
}

static uint32_t check_and_stream(uint32_t test, uint32_t result_event)
{
    uint32_t i, checksum = 0x811c9dc5u;
    for (i = 0; i < N; ++i)
        checksum = ((checksum << 5) | (checksum >> 27))
                   ^ (uint32_t)(uint16_t)product[i];
    if (checksum != expected_checksums[test]) {
        DEBUG[1] = checksum;
        DEBUG[0] = 0xdead0000u | (result_event << 8) | test;
        for (;;) __asm__ volatile ("nop");
    }
    for (i = 0; i < N; ++i) {
        DEBUG[12] = i;
        DEBUG[13] = (uint32_t)(uint16_t)product[i];
        event(result_event);
    }
    return checksum;
}

void benchmark_main(void)
{
    uint32_t test;
    DEBUG[0] = 0x52554e21u;
    DEBUG[1] = 0;
    DEBUG[10] = empty_bracket();

    for (test = 0; test < CPU_BENCHMARK_CASES; ++test) {
        uint32_t t0, t1, t2, t3, t4, t5, t6, checksum;
        generate_inputs(test);
        DEBUG[2] = test;
        event(1);
        stream_inputs();

        event(8);
        t0 = cycle();
        copy_inputs();
        sw_ntt(working_a);
        sw_ntt(working_b);
        sw_basemul(product, working_a, working_b);
        sw_invntt(product);
        sw_canonicalize(product);
        t6 = cycle();
        event(9);
        DEBUG[9] = t6 - t0;
        checksum = check_and_stream(test, 3);
        DEBUG[11] = checksum;
        event(4);

        event(10);
        t0 = cycle();
        copy_inputs();
        t1 = cycle();
        sw_ntt(working_a);
        t2 = cycle();
        sw_ntt(working_b);
        t3 = cycle();
        sw_basemul(product, working_a, working_b);
        t4 = cycle();
        sw_invntt(product);
        t5 = cycle();
        sw_canonicalize(product);
        t6 = cycle();
        event(11);
        DEBUG[3] = t1 - t0;
        DEBUG[4] = t2 - t1;
        DEBUG[5] = t3 - t2;
        DEBUG[6] = t4 - t3;
        DEBUG[7] = t5 - t4;
        DEBUG[8] = t6 - t5;
        DEBUG[9] = t6 - t0;
        checksum = check_and_stream(test, 5);
        DEBUG[11] = checksum;
        event(6);
        event(7);
    }
    DEBUG[0] = 0x600d600du;
    event(15);
    for (;;) __asm__ volatile ("nop");
}
