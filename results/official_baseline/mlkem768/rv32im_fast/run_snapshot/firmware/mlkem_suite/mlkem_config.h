#ifndef PICO_MLKEM_SUITE_CONFIG_H
#define PICO_MLKEM_SUITE_CONFIG_H

/* The build supplies MLKEM_LEVEL and MLKEM_NAMESPACE for one fixed level. */
#ifndef MLKEM_LEVEL
#error "MLKEM_LEVEL must be supplied as 512, 768, or 1024"
#endif
#ifndef MLKEM_NAMESPACE
#error "MLKEM_NAMESPACE must be supplied, e.g. pico_mlkem768"
#endif
#define MLK_CONFIG_PARAMETER_SET MLKEM_LEVEL
#define MLK_CONFIG_NAMESPACE_PREFIX MLKEM_NAMESPACE
#define MLK_CONFIG_NO_RANDOMIZED_API

#endif
