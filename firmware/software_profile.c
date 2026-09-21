#include <stdint.h>
#include "expected_words.h"

static int16_t a[256], b[256];
extern void software_polymul(int16_t *, int16_t *);
static inline void report(unsigned offset, uint32_t value)
{
    *(volatile uint32_t *)(0x50000000u+offset)=value;
}
static inline uint32_t cycle(void)
{
    uint32_t x;
    __asm__ volatile("rdcycle %0" : "=r"(x) : : "memory");
    return x;
}
void main(void)
{
    unsigned av=7, da=48, bv=19, db=40;
    for(unsigned i=0;i<256;++i) {
        a[i]=av; b[i]=bv;
        av+=da; if(av>=3329) av-=3329;
        da+=34; if(da>=3329) da-=3329;
        bv+=db; if(bv>=3329) bv-=3329;
        db+=58; if(db>=3329) db-=3329;
    }
    uint32_t r0=cycle(), r1=cycle(), t0=cycle();
    software_polymul(a,b);
    uint32_t t1=cycle();
    unsigned errors=0;
    for(unsigned i=0;i<128;++i) {
        uint32_t word=(uint16_t)a[2*i] | ((uint32_t)(uint16_t)a[2*i+1]<<16);
        if(word!=expected_words[i]) ++errors;
        report(20,word);
    }
    report(4,errors);
    report(8,t1-t0);
    report(12,r1-r0);
    report(16,(uint32_t)a);
    report(0,errors ? 0xdead0003u : 0x600d600du);
    for(;;) {}
}
