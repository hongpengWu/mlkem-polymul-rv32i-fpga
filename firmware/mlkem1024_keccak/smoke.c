#include "keccak_mmio.h"
#include "smoke_inputs.h"
#define DBG ((volatile uint32_t *)0x50000000u)
#define SENTINEL 0xa5a5a5a5u
static keccak_context contexts[2];
static uint32_t output[1024];

static uint32_t cycles(void)
{
    uint32_t value;
    __asm__ volatile("rdcycle %0" : "=r"(value) :: "memory");
    return value;
}

void kat_main(void)
{
    uint32_t sequence = 0;
    DBG[0] = 0x4b435052u;
    for (unsigned call = 0; call < SMOKE_CALLS; ++call) {
        const struct smoke_call *task = &smoke_calls[call];
        keccak_context *context = &contexts[task->context_id];
        uint32_t previous[KECCAK_CONTEXT_WORDS32];
        for (unsigned i = 0; i < KECCAK_CONTEXT_WORDS32; ++i)
            previous[i] = context->words[i];
        for (unsigned i = 0; i < 1024; ++i) output[i] = SENTINEL;
        keccak_metrics metrics;
        const uint32_t start = cycles();
        const int result = keccak_mmio_run(context, output, task->input,
            task->input_len, task->output_len, task->mode, task->command, &metrics);
        const uint32_t elapsed = cycles() - start;
        if (result <= KECCAK_DRIVER_TIMEOUT) {
            DBG[5] = (uint32_t)result;
            DBG[0] = 0x4b435046u;
            for (;;) {}
        }
        uint32_t context_ok = 1;
        for (unsigned i = 0; i < KECCAK_CONTEXT_WORDS32; ++i) {
            if (result && context->words[i] != previous[i]) context_ok = 0;
            if (!result && (task->command == KECCAK_CLEAR || task->mode >= 2u)
                && context->words[i] != 0u) context_ok = 0;
        }
        DBG[1] = call;
        DBG[4] = elapsed;
        DBG[5] = (uint32_t)result;
        DBG[6] = metrics.starts;
        DBG[7] = metrics.busy_cycles;
        DBG[8] = metrics.buffer_writes;
        DBG[9] = metrics.buffer_reads;
        DBG[10] = metrics.flags;
        DBG[11] = task->output_len;
        DBG[12] = context_ok;
        for (unsigned word = 0; word < (task->output_len + 3u)/4u; ++word) {
            DBG[2] = word;
            DBG[3] = output[word];
            DBG[15] = ++sequence;
        }
        DBG[14] = call + 1u;
    }
    DBG[0] = 0x4b435050u;
}
