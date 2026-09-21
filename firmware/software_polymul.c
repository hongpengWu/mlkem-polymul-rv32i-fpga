#include <stdint.h>

/* Same Montgomery zetas as the existing HLS core. */
static const int16_t zetas[128] = {
 -1044,-758,-359,-1517,1493,1422,287,202,-171,622,1577,182,962,-1202,-1474,1468,
 573,-1325,264,383,-829,1458,-1602,-130,-681,1017,732,608,-1542,411,-205,-1571,
 1223,652,-552,1015,-1293,1491,-282,-1544,516,-8,-320,-666,-1618,-1162,126,1469,
 -853,-90,-271,830,107,-1421,-247,-951,-398,961,-1508,-725,448,-1065,677,-1275,
 -1103,430,555,843,-1251,871,1550,105,422,587,177,-235,-291,-460,1574,1653,
 -246,778,1159,-147,-777,1483,-602,1119,-1590,644,-872,349,418,329,-156,-75,
 817,1097,603,610,1322,-1285,-1465,384,-1215,-136,1218,-1335,-874,220,-1187,-1659,
 -1185,-1530,-1278,794,-1510,-854,-870,478,-108,-308,996,991,958,-1460,1522,1628
};

static int16_t norm(int32_t x)
{
    if (x < 0) x += 3329;
    if (x >= 3329) x -= 3329;
    return (int16_t)x;
}

static __attribute__((noinline)) int16_t fqmul(int16_t a, int16_t b)
{
    int32_t p = (int32_t)a * b;
    int16_t t = (int16_t)((uint32_t)p * 62209u);
    return norm((p - (int32_t)t * 3329) >> 16);
}

static void ntt(int16_t a[256])
{
    unsigned k = 1;
    for (unsigned len = 128; len >= 2; len >>= 1)
        for (unsigned start = 0; start < 256; start += 2*len) {
            int16_t z = zetas[k++];
            for (unsigned j = start; j < start+len; ++j) {
                int16_t t = fqmul(z, a[j+len]);
                int16_t u = a[j];
                a[j] = norm(u+t);
                a[j+len] = norm(u-t);
            }
        }
}

/* Inputs may be overwritten; output replaces a, as in hardware readback. */
void software_polymul(int16_t a[256], int16_t b[256])
{
    ntt(a);
    ntt(b);
    for (unsigned i = 0; i < 128; ++i) {
        int16_t z = zetas[64+(i>>1)];
        if (i & 1) z = -z;
        int16_t a0=a[2*i], a1=a[2*i+1], b0=b[2*i], b1=b[2*i+1];
        a[2*i] = norm(fqmul(fqmul(a1,b1),z) + fqmul(a0,b0));
        a[2*i+1] = norm(fqmul(a0,b1) + fqmul(a1,b0));
    }
    unsigned k = 127;
    for (unsigned len = 2; len <= 128; len <<= 1)
        for (unsigned start = 0; start < 256; start += 2*len) {
            int16_t z=zetas[k--];
            for (unsigned j=start; j<start+len; ++j) {
                int16_t u=a[j], v=a[j+len];
                a[j]=norm(u+v);
                a[j+len]=fqmul(z,norm(v-u));
            }
        }
    /* 1441 = R^2 / 128 mod q; cancels BaseMul's R^-1 factor. */
    for (unsigned i=0; i<256; ++i) a[i]=fqmul(a[i],1441);
}
