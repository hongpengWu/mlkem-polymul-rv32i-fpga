#include <ap_int.h>
#include <hls_stream.h>

typedef ap_int<16> coeff_t;
typedef ap_uint<12> residue_t;
typedef ap_uint<24> pair_t;

static const int Q39C = 3329;
static const coeff_t zetas39c[128] = {
  -1044, -758, -359, -1517, 1493, 1422, 287, 202,
  -171, 622, 1577, 182, 962, -1202, -1474, 1468,
  573, -1325, 264, 383, -829, 1458, -1602, -130,
  -681, 1017, 732, 608, -1542, 411, -205, -1571,
  1223, 652, -552, 1015, -1293, 1491, -282, -1544,
  516, -8, -320, -666, -1618, -1162, 126, 1469,
  -853, -90, -271, 830, 107, -1421, -247, -951,
  -398, 961, -1508, -725, 448, -1065, 677, -1275,
  -1103, 430, 555, 843, -1251, 871, 1550, 105,
  422, 587, 177, -235, -291, -460, 1574, 1653,
  -246, 778, 1159, -147, -777, 1483, -602, 1119,
  -1590, 644, -872, 349, 418, 329, -156, -75,
  817, 1097, 603, 610, 1322, -1285, -1465, 384,
  -1215, -136, 1218, -1335, -874, 220, -1187, -1659,
  -1185, -1530, -1278, 794, -1510, -854, -870, 478,
  -108, -308, 996, 991, 958, -1460, 1522, 1628
};

enum mode39c { MODE_FNTT39C=0, MODE_BM39C=1, MODE_INTT39C=2, MODE_SCALE39C=3 };

struct req39c {
    residue_t a, b, aux;
    ap_uint<24> direct_product;
    ap_uint<8> addr;
    ap_uint<4> tag;
    ap_uint<2> mode;
    bool use_direct;
    bool dst_ping;
};

struct rsp39c {
    residue_t reduced, aux;
    ap_uint<8> addr;
    ap_uint<4> tag;
    ap_uint<2> mode;
    bool dst_ping;
};

static residue_t norm39c(coeff_t x) {
    #pragma HLS INLINE
    ap_int<17> y=x; if(y<0)y+=Q39C; if(y>=Q39C)y-=Q39C; return (residue_t)y;
}
static residue_t add39c(residue_t a,residue_t b) {
    #pragma HLS INLINE
    ap_uint<13> s=(ap_uint<13>)a+b; if(s>=Q39C)s-=Q39C; return (residue_t)s;
}
static residue_t sub39c(residue_t a,residue_t b) {
    #pragma HLS INLINE
    ap_int<14> d=(ap_int<14>)a-b; if(d<0)d+=Q39C; return (residue_t)d;
}
static residue_t lo39c(pair_t x) {
    #pragma HLS INLINE
    return (residue_t)x.range(11,0);
}
static residue_t hi39c(pair_t x) {
    #pragma HLS INLINE
    return (residue_t)x.range(23,12);
}
static pair_t pack39c(residue_t l,residue_t h) {
    #pragma HLS INLINE
    pair_t x=0; x.range(11,0)=l; x.range(23,12)=h; return x;
}

static void issue39c(const pair_t ping[128], const pair_t pong[128],
                     const pair_t ant[128], const pair_t bnt[128],
                     const residue_t bm[10][64],
                     int mode, int len, int zparam, int group,
                     bool src_ping, hls::stream<req39c> &rq) {
    int block=0, offset=0, start=0, pair_base=0;
issue39c_loop:
    for(int n=0;n<128;++n) {
        #pragma HLS PIPELINE II=1
        req39c r={}; r.mode=(ap_uint<2>)mode; r.dst_ping=!src_ping;
        if(mode==MODE_FNTT39C) {
            int current=start>>1, j=current+offset; residue_t u,v;
            if(len==128) { pair_t w=src_ping?ping[j]:pong[j]; u=lo39c(w);v=hi39c(w); }
            else {
                int prev=current-((block&1)?len:0);
                pair_t wu=src_ping?ping[prev+offset]:pong[prev+offset];
                pair_t wv=src_ping?ping[prev+len+offset]:pong[prev+len+offset];
                if((block&1)==0){u=lo39c(wu);v=lo39c(wv);}else{u=hi39c(wu);v=hi39c(wv);}
            }
            r.a=norm39c(zetas39c[zparam+block]); r.b=v; r.aux=u; r.addr=j;
            if(offset==len-1){offset=0;++block;start+=(len<<1);}else ++offset;
        } else if(mode==MODE_INTT39C) {
            int prevlen=len>>1; residue_t u,v;
            if(len==2) { pair_t w=src_ping?ping[pair_base+offset]:pong[pair_base+offset];u=lo39c(w);v=hi39c(w); }
            else {
                int lane=offset<prevlen?offset:offset-prevlen;
                pair_t wu=src_ping?ping[pair_base+lane]:pong[pair_base+lane];
                pair_t wv=src_ping?ping[pair_base+prevlen+lane]:pong[pair_base+prevlen+lane];
                if(offset<prevlen){u=lo39c(wu);v=lo39c(wv);}else{u=hi39c(wu);v=hi39c(wv);}
            }
            r.a=norm39c(zetas39c[zparam-block]); r.b=sub39c(v,u); r.aux=add39c(u,v);
            r.addr=pair_base+offset;
            if(offset==len-1){offset=0;++block;pair_base+=len;}else ++offset;
        } else if(mode==MODE_BM39C) {
            int bi=n>>1, lane=n&1; pair_t aw0=ant[bi<<1],aw1=ant[(bi<<1)+1];
            pair_t bw0=bnt[bi<<1],bw1=bnt[(bi<<1)+1];
            residue_t a0=lo39c(aw0),a1=lo39c(aw1),a2=hi39c(aw0),a3=hi39c(aw1);
            residue_t b0=lo39c(bw0),b1=lo39c(bw1),b2=hi39c(bw0),b3=hi39c(bw1);
            if(group==0){r.a=lane?a0:a1;r.b=lane?b0:b1;r.tag=lane?1:0;}
            else if(group==1){r.a=lane?a1:a0;r.b=lane?b0:b1;r.tag=lane?3:2;}
            else if(group==2){r.a=lane?a2:a3;r.b=lane?b2:b3;r.tag=lane?5:4;}
            else if(group==3){r.a=lane?a3:a2;r.b=lane?b2:b3;r.tag=lane?7:6;}
            else { residue_t z=norm39c(zetas39c[64+bi]); r.a=lane?bm[4][bi]:bm[0][bi];
                   r.b=lane?(z?(residue_t)(Q39C-z):(residue_t)0):z; r.tag=lane?9:8; }
            r.addr=bi;
        } else {
            int idx=zparam+n; pair_t w=pong[n]; residue_t x=(idx<128)?lo39c(w):hi39c(w);
            ap_uint<24> xw=x;
            r.direct_product=(xw<<10)+(xw<<8)+(xw<<7)+(xw<<5)+xw;
            r.use_direct=true; r.addr=idx;
        }
        rq.write(r);
    }
}

static void pe39c(hls::stream<req39c> &rq,hls::stream<rsp39c> &rs) {
pe39c_loop:
    for(int n=0;n<128;++n) {
        #pragma HLS PIPELINE II=1
        req39c r=rq.read();
        ap_uint<24> dp=(ap_uint<24>)r.a*r.b;
        #pragma HLS BIND_OP variable=dp op=mul impl=dsp latency=2
        ap_uint<24> p=r.use_direct?r.direct_product:dp;
        ap_uint<8> l1=p.range(7,0); ap_uint<16> h1=p.range(23,8);
        // V39-E: keep the K^2-RED constant multipliers in LUT fabric.
        // V39-D expressed 13*x as shifts/adds, but Vivado reassociated both
        // expressions into DSP48E1 multipliers during RTL implementation.
        ap_int<18> m1=(ap_int<18>)l1*13;
        #pragma HLS BIND_OP variable=m1 op=mul impl=fabric latency=1
        ap_int<18> k1=m1-(ap_int<18>)h1;
        #pragma HLS BIND_OP variable=k1 op=sub impl=fabric latency=1
        ap_uint<16> bits=(ap_uint<16>)k1; ap_uint<8> l2=bits.range(7,0),h2=bits.range(15,8);
        ap_int<14> m2=(ap_int<14>)l2*13;
        #pragma HLS BIND_OP variable=m2 op=mul impl=fabric latency=1
        ap_int<14> k2=m2-(ap_int<14>)h2;
        #pragma HLS BIND_OP variable=k2 op=sub impl=fabric latency=1
        ap_int<15> c=k2; if(k1<0)c+=(k2>=3073)?-3073:256;else if(k2<0)c+=Q39C;
        rsp39c s; s.reduced=(residue_t)c;s.aux=r.aux;s.addr=r.addr;s.tag=r.tag;
        s.mode=r.mode;s.dst_ping=r.dst_ping;rs.write(s);
    }
}

static void write39c(pair_t ping[128],pair_t pong[128],residue_t bm[10][64],
                     coeff_t output[256],hls::stream<rsp39c> &rs) {
write39c_loop:
    for(int n=0;n<128;++n) {
        #pragma HLS PIPELINE II=1
        rsp39c s=rs.read();
        if(s.mode==MODE_FNTT39C) {
            pair_t w=pack39c(add39c(s.aux,s.reduced),sub39c(s.aux,s.reduced));
            if(s.dst_ping)ping[s.addr]=w;else pong[s.addr]=w;
        } else if(s.mode==MODE_INTT39C) {
            pair_t w=pack39c(s.aux,s.reduced);
            if(s.dst_ping)ping[s.addr]=w;else pong[s.addr]=w;
        } else if(s.mode==MODE_BM39C) bm[s.tag][s.addr]=s.reduced;
        else output[s.addr]=(coeff_t)s.reduced;
    }
}

static void batch39c(pair_t ping[128],pair_t pong[128],const pair_t ant[128],
                     const pair_t bnt[128],residue_t bm[10][64],coeff_t output[256],
                     int mode,int len,int zparam,int group,bool src_ping) {
    #pragma HLS INLINE off
    #pragma HLS DATAFLOW
    hls::stream<req39c> rq("rq39c"); hls::stream<rsp39c> rs("rs39c");
    #pragma HLS STREAM variable=rq depth=2
    #pragma HLS STREAM variable=rs depth=2
    issue39c(ping,pong,ant,bnt,bm,mode,len,zparam,group,src_ping,rq);
    pe39c(rq,rs);
    write39c(ping,pong,bm,output,rs);
}

#ifndef V39C_SUPPRESS_TOP
void mlkem_poly_mul256_v39c_unified_stream_batch(const coeff_t a[256],
        const coeff_t b[256],coeff_t output[256]) {
    pair_t ping[128],pong[128],ant[128],bnt[128]; residue_t bm[10][64];
    #pragma HLS BIND_STORAGE variable=ping type=ram_t2p impl=bram
    #pragma HLS BIND_STORAGE variable=pong type=ram_t2p impl=bram
    #pragma HLS BIND_STORAGE variable=ant type=ram_t2p impl=bram
    #pragma HLS BIND_STORAGE variable=bnt type=ram_t2p impl=bram
    #pragma HLS ARRAY_PARTITION variable=bm complete dim=1
    #pragma HLS BIND_STORAGE variable=bm type=ram_1p impl=lutram
    #pragma HLS BIND_STORAGE variable=zetas39c type=rom_2p impl=bram
    #pragma HLS ALLOCATION function instances=batch39c limit=1

load_a39c: for(int i=0;i<128;++i){
        #pragma HLS PIPELINE II=1
        ping[i]=pack39c(norm39c(a[i]),norm39c(a[i+128]));
    }
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,128,1,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,64,2,0,false);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,32,4,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,16,8,0,false);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,8,16,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,4,32,0,false);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,2,64,0,true);
save_a39c: for(int i=0;i<128;++i){
        #pragma HLS PIPELINE II=1
        ant[i]=pong[i];
    }
load_b39c: for(int i=0;i<128;++i){
        #pragma HLS PIPELINE II=1
        ping[i]=pack39c(norm39c(b[i]),norm39c(b[i+128]));
    }
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,128,1,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,64,2,0,false);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,32,4,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,16,8,0,false);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,8,16,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,4,32,0,false);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_FNTT39C,2,64,0,true);
save_b39c: for(int i=0;i<128;++i){
        #pragma HLS PIPELINE II=1
        bnt[i]=pong[i];
    }
    batch39c(ping,pong,ant,bnt,bm,output,MODE_BM39C,0,0,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_BM39C,0,0,1,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_BM39C,0,0,2,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_BM39C,0,0,3,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_BM39C,0,0,4,true);
pack_product39c: for(int i=0;i<64;++i){
        #pragma HLS PIPELINE II=1
        ant[i<<1]=pack39c(add39c(bm[8][i],bm[1][i]),add39c(bm[9][i],bm[5][i]));
        ant[(i<<1)+1]=pack39c(add39c(bm[2][i],bm[3][i]),add39c(bm[6][i],bm[7][i]));
    }
load_intt39c: for(int i=0;i<128;++i){
        #pragma HLS PIPELINE II=1
        ping[i]=ant[i];
    }
    batch39c(ping,pong,ant,bnt,bm,output,MODE_INTT39C,2,127,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_INTT39C,4,63,0,false);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_INTT39C,8,31,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_INTT39C,16,15,0,false);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_INTT39C,32,7,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_INTT39C,64,3,0,false);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_INTT39C,128,1,0,true);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_SCALE39C,0,0,0,false);
    batch39c(ping,pong,ant,bnt,bm,output,MODE_SCALE39C,0,128,0,false);
}
#endif
