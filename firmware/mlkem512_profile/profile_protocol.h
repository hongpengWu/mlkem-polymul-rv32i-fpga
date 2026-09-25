#ifndef MLKEM512_PROFILE_PROTOCOL_H
#define MLKEM512_PROFILE_PROTOCOL_H
#include <stdint.h>

/* Profiling-only marker port: DEBUG_VALID is unused inside the API window.
 * The passive TB maintains the nested timers. No extra rdcycle instructions
 * or expected outputs are added to the cryptographic implementation. */
extern volatile uint32_t mlkem_profile_enabled;
#define PROFILE_PORT (*(volatile uint32_t *)UINT32_C(0x50000038))

static inline __attribute__((always_inline)) uint32_t profile_enter(uint32_t id)
{
    if (!mlkem_profile_enabled) return 0;
    __asm__ volatile ("" : : : "memory");
    PROFILE_PORT = UINT32_C(0x30000000) | id;
    return id;
}

static inline __attribute__((always_inline)) void profile_leave(uint32_t *id)
{
    if (*id) {
        __asm__ volatile ("" : : : "memory");
        PROFILE_PORT = UINT32_C(0x40000000) | *id;
    }
}

/* GCC cleanup covers all returns and cleanup labels, including inlined bodies. */
#define PROFILE_SCOPE(id) \
    uint32_t profile_scope_token __attribute__((cleanup(profile_leave))) = profile_enter(id)
#endif
