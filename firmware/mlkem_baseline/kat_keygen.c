/*
 * Minimal deterministic ML-KEM keyGen harness for PicoRV32.
 *
 * This file deliberately contains no ML-KEM implementation.  The API
 * is supplied by the pinned portable mlkem-native source without modifying its
 * algorithms.  Keeping the harness independent lets the same protocol be used
 * for RV32I, RV32IM iterative, RV32IM fast, and CPU+accelerator builds.
 */

#include <stdint.h>

#include "mlkem_native.h"
#include "kat_protocol.h"
#include "mlkem512_keygen.h"

#define KAT_ERR_API UINT32_C(2)

_Static_assert(MLK_CONFIG_PARAMETER_SET == KAT_KEYGEN_PARAMETER_SET,
               "ML-KEM implementation and vector parameter sets differ");
_Static_assert(MLKEM_PUBLICKEYBYTES(MLK_CONFIG_PARAMETER_SET) == KAT_KEYGEN_EK_BYTES,
               "ML-KEM encapsulation key length differs from vector");
_Static_assert(MLKEM_SECRETKEYBYTES(MLK_CONFIG_PARAMETER_SET) == KAT_KEYGEN_DK_BYTES,
               "ML-KEM decapsulation key length differs from vector");

static uint8_t output_ek[KAT_KEYGEN_EK_BYTES];
static uint8_t output_dk[KAT_KEYGEN_DK_BYTES];
static uint8_t coins[2u * KAT_KEYGEN_SEED_BYTES];

static uint32_t empty_bracket(void)
{
    uint32_t start, stop;
    __asm__ volatile ("rdcycle %0\n\trdcycle %1"
                      : "=&r"(start), "=r"(stop) : : "memory");
    return stop - start;
}

static void halt_failure(uint32_t code)
{
    KAT_DEBUG_ERROR = code;
    KAT_DEBUG_STATUS = KAT_STATUS_FAIL;
    KAT_DEBUG_EVENT = KAT_EVENT_DONE;
    for (;;)
        __asm__ volatile ("nop");
}

void kat_main(void)
{
    uint32_t case_index;

    KAT_DEBUG_STATUS = KAT_STATUS_RUN;
    KAT_DEBUG_ERROR = 0;
    KAT_DEBUG_AUX0 = KAT_KEYGEN_PARAMETER_SET;
    KAT_DEBUG_AUX1 = KAT_KEYGEN_EK_BYTES;
    KAT_DEBUG_AUX2 = KAT_KEYGEN_DK_BYTES;
    KAT_DEBUG_AUX3 = KAT_KEYGEN_CASE_COUNT;
    KAT_DEBUG_AUX4 = empty_bracket();

    for (case_index = 0; case_index < KAT_KEYGEN_CASE_COUNT; ++case_index) {
        const kat_keygen_case_t *test = &kat_keygen_cases[case_index];
        uint32_t start, stop;
        int result;

        KAT_DEBUG_CASE = test->tc_id;
        kat_emit(KAT_EVENT_CASE_BEGIN, 0, (const uint8_t *)0, 0);

        /* ACVP lists z then d.  ML-KEM.KeyGen_Internal consumes coins d||z. */
        for (uint32_t i = 0; i < KAT_KEYGEN_SEED_BYTES; ++i) {
            coins[i] = test->d[i];
            coins[KAT_KEYGEN_SEED_BYTES + i] = test->z[i];
        }
        kat_emit_bytes(KAT_EVENT_INPUT_D, coins, KAT_KEYGEN_SEED_BYTES);
        kat_emit_bytes(KAT_EVENT_INPUT_Z, coins + KAT_KEYGEN_SEED_BYTES,
                       KAT_KEYGEN_SEED_BYTES);

        KAT_DEBUG_EVENT = KAT_EVENT_MEASURE_BEGIN;
        start = kat_cycle();
        /* mlkem_native.h declares the configured namespace then cleans up
         * its helper macros, so call the public symbol declared by it. */
        result = pico_mlkem512_keypair_derand(output_ek, output_dk, coins);
        stop = kat_cycle();
        KAT_DEBUG_EVENT = KAT_EVENT_MEASURE_END;
        KAT_DEBUG_CYCLES = stop - start;
        KAT_DEBUG_AUX5 = (uint32_t)result;
        if (result != 0)
            halt_failure(KAT_ERR_API | ((uint32_t)(uint16_t)(-result) << 16));

        kat_emit_bytes(KAT_EVENT_EK, output_ek, KAT_KEYGEN_EK_BYTES);
        kat_emit_bytes(KAT_EVENT_DK, output_dk, KAT_KEYGEN_DK_BYTES);
        kat_emit(KAT_EVENT_CASE_END, 0, (const uint8_t *)0, 0);
    }

    KAT_DEBUG_STATUS = KAT_STATUS_PASS;
    KAT_DEBUG_EVENT = KAT_EVENT_DONE;
    for (;;)
        __asm__ volatile ("nop");
}
