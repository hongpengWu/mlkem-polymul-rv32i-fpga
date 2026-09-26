/* Freestanding byte-oriented C runtime.  Build with -fno-builtin and
 * -fno-tree-loop-distribute-patterns to prevent recursion via synthesized
 * calls to memcpy/memset.  These functions use no heap or system calls. */

#include <stddef.h>

void *memcpy(void *destination, const void *source, size_t count)
{
    unsigned char *dst = (unsigned char *)destination;
    const unsigned char *src = (const unsigned char *)source;
    size_t i;
    for (i = 0; i < count; ++i)
        dst[i] = src[i];
    return destination;
}

void *memset(void *destination, int value, size_t count)
{
    unsigned char *dst = (unsigned char *)destination;
    size_t i;
    for (i = 0; i < count; ++i)
        dst[i] = (unsigned char)value;
    return destination;
}
