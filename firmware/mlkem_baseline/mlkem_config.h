#ifndef PICO_MLKEM_CONFIG_H
#define PICO_MLKEM_CONFIG_H

/* Select the same portable C algorithms for both -march=rv32i and rv32im.
 * Native arithmetic/FIPS202 backend flags are deliberately absent.  Inline
 * compiler value barriers and the default zeroization barrier remain enabled;
 * these are not ISA-specific accelerated implementations. */
#define MLK_CONFIG_PARAMETER_SET 512
#define MLK_CONFIG_NAMESPACE_PREFIX pico_mlkem512
#define MLK_CONFIG_NO_RANDOMIZED_API
#define MLK_CONFIG_NO_ENCAPS_API
#define MLK_CONFIG_NO_DECAPS_API

#endif /* PICO_MLKEM_CONFIG_H */
