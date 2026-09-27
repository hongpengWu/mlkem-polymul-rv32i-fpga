#include "keccak_mmio.h"
#define REG(offset) (*(volatile uint32_t *)(KECCAK_MMIO_BASE + (offset)))
#define POLL_LIMIT 200000u

static void metrics_read(keccak_metrics *metrics)
{
    if (!metrics) return;
    metrics->starts = REG(0x100u);
    metrics->busy_cycles = REG(0x104u);
    metrics->buffer_writes = REG(0x108u);
    metrics->buffer_reads = REG(0x10cu);
    metrics->flags = REG(0x110u);
}

int keccak_mmio_run(keccak_context *context, uint32_t *output,
                   const uint32_t *input, uint32_t input_len,
                   uint32_t output_len, uint32_t mode, uint32_t command,
                   keccak_metrics *metrics)
{
    if (!context || input_len > 2048u || output_len > 4096u ||
        (input_len && !input) || (output_len && !output))
        return KECCAK_DRIVER_ARGUMENT;

    /* ISR is toggle-on-write. Never write 1 when no interrupt is pending. */
    REG(0x04u) = 1u;
    REG(0x08u) = 1u;
    if (REG(0x0cu) & 1u) REG(0x0cu) = 1u;
    for (unsigned i = 0; i < KECCAK_CONTEXT_WORDS32; ++i)
        REG(0x3000u + 4u*i) = context->words[i];
    for (unsigned i = 0; i < (input_len + 3u)/4u; ++i)
        REG(0x1000u + 4u*i) = input[i];
    REG(0x18u) = input_len;
    REG(0x20u) = output_len;
    REG(0x28u) = mode;
    REG(0x30u) = command;
    REG(0x00u) = 1u;
    unsigned poll;
    for (poll = 0; poll < POLL_LIMIT; ++poll)
        if (REG(0x0cu) & 1u) break;
    if (poll == POLL_LIMIT) {
        metrics_read(metrics);
        return KECCAK_DRIVER_TIMEOUT;
    }
    const int result = (int32_t)REG(0x10u);
    REG(0x0cu) = 1u; /* Pending completion was observed above. */
    for (unsigned i = 0; i < KECCAK_CONTEXT_WORDS32; ++i)
        context->words[i] = REG(0x3000u + 4u*i);
    if (result == 0)
        for (unsigned i = 0; i < (output_len + 3u)/4u; ++i)
            output[i] = REG(0x2000u + 4u*i);
    metrics_read(metrics);
    return result;
}
