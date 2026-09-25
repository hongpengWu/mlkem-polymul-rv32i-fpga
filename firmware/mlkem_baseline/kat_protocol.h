#ifndef KAT_KEYGEN_PROTOCOL_H
#define KAT_KEYGEN_PROTOCOL_H

/*
 * PicoRV32 ML-KEM KAT stream protocol.
 *
 * The CPU system currently exposes only the 16-word debug window at
 * 0x5000_0000.  A stream record is committed by writing DEBUG_EVENT last;
 * the monitor samples DEBUG_INDEX, DEBUG_DATA and DEBUG_VALID before accepting
 * the event.  Payloads are little-endian 32-bit words.  The valid byte count
 * is 1..4 (all current ML-KEM-512 key sizes are word aligned).
 */

#include <stdint.h>

#define KAT_DEBUG_BASE        UINT32_C(0x50000000)
#define KAT_DEBUG_STATUS      (*(volatile uint32_t *)(KAT_DEBUG_BASE + 0u))
#define KAT_DEBUG_ERROR       (*(volatile uint32_t *)(KAT_DEBUG_BASE + 4u))
#define KAT_DEBUG_CASE        (*(volatile uint32_t *)(KAT_DEBUG_BASE + 8u))
#define KAT_DEBUG_CYCLES      (*(volatile uint32_t *)(KAT_DEBUG_BASE + 12u))
#define KAT_DEBUG_AUX0        (*(volatile uint32_t *)(KAT_DEBUG_BASE + 16u))
#define KAT_DEBUG_AUX1        (*(volatile uint32_t *)(KAT_DEBUG_BASE + 20u))
#define KAT_DEBUG_AUX2        (*(volatile uint32_t *)(KAT_DEBUG_BASE + 24u))
#define KAT_DEBUG_AUX3        (*(volatile uint32_t *)(KAT_DEBUG_BASE + 28u))
#define KAT_DEBUG_AUX4        (*(volatile uint32_t *)(KAT_DEBUG_BASE + 32u))
#define KAT_DEBUG_AUX5        (*(volatile uint32_t *)(KAT_DEBUG_BASE + 36u))
#define KAT_DEBUG_INDEX       (*(volatile uint32_t *)(KAT_DEBUG_BASE + 48u))
#define KAT_DEBUG_DATA        (*(volatile uint32_t *)(KAT_DEBUG_BASE + 52u))
#define KAT_DEBUG_VALID       (*(volatile uint32_t *)(KAT_DEBUG_BASE + 56u))
#define KAT_DEBUG_EVENT       (*(volatile uint32_t *)(KAT_DEBUG_BASE + 60u))

#define KAT_STATUS_RUN        UINT32_C(0x4b415452) /* "KATR" */
#define KAT_STATUS_PASS       UINT32_C(0x4b415450) /* "KATP" */
#define KAT_STATUS_FAIL       UINT32_C(0x4b415446) /* "KATF" */

#define KAT_EVENT_CASE_BEGIN  UINT32_C(0x100)
#define KAT_EVENT_INPUT_D    UINT32_C(0x101)
#define KAT_EVENT_INPUT_Z    UINT32_C(0x102)
#define KAT_EVENT_EK         UINT32_C(0x103)
#define KAT_EVENT_DK         UINT32_C(0x104)
#define KAT_EVENT_CASE_END   UINT32_C(0x105)
#define KAT_EVENT_MEASURE_BEGIN UINT32_C(0x108)
#define KAT_EVENT_MEASURE_END UINT32_C(0x109)
#define KAT_EVENT_DONE       UINT32_C(0x1ff)

static inline uint32_t kat_pack_le(const uint8_t *p, uint32_t count)
{
    uint32_t out = 0;
    uint32_t i;
    for (i = 0; i < count; ++i)
        out |= (uint32_t)p[i] << (8u * i);
    return out;
}

static inline uint32_t kat_cycle(void)
{
    uint32_t value;
    __asm__ volatile ("rdcycle %0" : "=r"(value) : : "memory");
    return value;
}

/* Write all record fields before DEBUG_EVENT so the event is an atomic marker
 * for the passive simulation monitor. */
static inline void kat_emit(uint32_t event, uint32_t index,
                            const uint8_t *bytes, uint32_t valid)
{
    KAT_DEBUG_INDEX = index;
    KAT_DEBUG_DATA = kat_pack_le(bytes, valid);
    KAT_DEBUG_VALID = valid;
    KAT_DEBUG_EVENT = event;
}

static inline void kat_emit_bytes(uint32_t event, const uint8_t *bytes,
                                  uint32_t byte_count)
{
    uint32_t index = 0;
    while (index < byte_count) {
        uint32_t remaining = byte_count - index;
        uint32_t valid = remaining < 4u ? remaining : 4u;
        kat_emit(event, index / 4u, bytes + index, valid);
        index += valid;
    }
}

#endif /* KAT_KEYGEN_PROTOCOL_H */
