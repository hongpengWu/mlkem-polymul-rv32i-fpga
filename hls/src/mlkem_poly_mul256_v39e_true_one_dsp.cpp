#define V39C_SUPPRESS_TOP
#include "mlkem_poly_mul256_v39e_unified_stream_support.cpp"

static void issue39d(const pair_t src[128], const pair_t ant[128],
                     const pair_t bnt[128], const residue_t bm_in[8][64],
                     int mode,int len,int zparam,int group,
                     hls::stream<req39c> &rq) {
    int block=0,offset=0,start=0,pair_base=0;
issue39d_loop:
    for(int n=0;n<128;++n) {
        #pragma HLS PIPELINE II=1
        req39c r={}; r.mode=mode; r.dst_ping=false;
        if(mode==MODE_FNTT39C) {
            int current=start>>1,j=current+offset; residue_t u,v;
            if(len==128){pair_t w=src[j];u=lo39c(w);v=hi39c(w);}
            else {int prev=current-((block&1)?len:0);pair_t wu=src[prev+offset];pair_t wv=src[prev+len+offset];
                  if((block&1)==0){u=lo39c(wu);v=lo39c(wv);}else{u=hi39c(wu);v=hi39c(wv);}}
            r.a=norm39c(zetas39c[zparam+block]);r.b=v;r.aux=u;r.addr=j;
            if(offset==len-1){offset=0;++block;start+=(len<<1);}else ++offset;
        } else if(mode==MODE_INTT39C) {
            int prevlen=len>>1;residue_t u,v;
            if(len==2){pair_t w=src[pair_base+offset];u=lo39c(w);v=hi39c(w);}
            else {int lane=offset<prevlen?offset:offset-prevlen;pair_t wu=src[pair_base+lane];pair_t wv=src[pair_base+prevlen+lane];
                  if(offset<prevlen){u=lo39c(wu);v=lo39c(wv);}else{u=hi39c(wu);v=hi39c(wv);}}
            r.a=norm39c(zetas39c[zparam-block]);r.b=sub39c(v,u);r.aux=add39c(u,v);r.addr=pair_base+offset;
            if(offset==len-1){offset=0;++block;pair_base+=len;}else ++offset;
        } else if(mode==MODE_BM39C) {
            int bi=n>>1,lane=n&1; r.addr=bi;
            if(group<4) {
                int ai,biw; bool ah,bh;
                if(group==0){ai=(bi<<1)+(lane?0:1);biw=(bi<<1)+(lane?0:1);ah=false;bh=false;r.tag=lane?1:0;}
                else if(group==1){ai=(bi<<1)+(lane?1:0);biw=(bi<<1)+(lane?0:1);ah=false;bh=false;r.tag=lane?3:2;}
                else if(group==2){ai=(bi<<1)+(lane?0:1);biw=(bi<<1)+(lane?0:1);ah=true;bh=true;r.tag=lane?5:4;}
                else {ai=(bi<<1)+(lane?1:0);biw=(bi<<1)+(lane?0:1);ah=true;bh=true;r.tag=lane?7:6;}
                pair_t aw=ant[ai],bw=bnt[biw];r.a=ah?hi39c(aw):lo39c(aw);r.b=bh?hi39c(bw):lo39c(bw);
            } else {residue_t z=norm39c(zetas39c[64+bi]);r.a=lane?bm_in[4][bi]:bm_in[0][bi];
                    r.b=lane?(z?(residue_t)(Q39C-z):(residue_t)0):z;r.tag=lane?9:8;}
        } else {
            int idx=zparam+n;pair_t w=src[n];residue_t x=idx<128?lo39c(w):hi39c(w);ap_uint<24>xw=x;
            ap_uint<24>a0=(xw<<10)+(xw<<8);ap_uint<24>a1=a0+(xw<<7);ap_uint<24>a2=a1+(xw<<5);
            ap_uint<24> direct=a2+xw;
            #pragma HLS BIND_OP variable=a0 op=add impl=fabric
            #pragma HLS BIND_OP variable=a1 op=add impl=fabric
            #pragma HLS BIND_OP variable=a2 op=add impl=fabric
            #pragma HLS BIND_OP variable=direct op=add impl=fabric
            r.direct_product=direct;r.use_direct=true;r.addr=idx;
        }
        rq.write(r);
    }
}

static void write39d(pair_t dst[128],residue_t bm_out[8][64],
                     residue_t bm_final[2][64],coeff_t output[256],int group,
                     hls::stream<rsp39c> &rs) {
write39d_loop:
    for(int n=0;n<128;++n){
        #pragma HLS PIPELINE II=1
        rsp39c s=rs.read();
        if(s.mode==MODE_FNTT39C)dst[s.addr]=pack39c(add39c(s.aux,s.reduced),sub39c(s.aux,s.reduced));
        else if(s.mode==MODE_INTT39C)dst[s.addr]=pack39c(s.aux,s.reduced);
        else if(s.mode==MODE_BM39C){if(group<4)bm_out[s.tag][s.addr]=s.reduced;else bm_final[s.tag-8][s.addr]=s.reduced;}
        else output[s.addr]=(coeff_t)s.reduced;
    }
}

static void batch39d(const pair_t src[128],pair_t dst[128],const pair_t ant[128],
                     const pair_t bnt[128],const residue_t bm_in[8][64],
                     residue_t bm_out[8][64],residue_t bm_final[2][64],
                     coeff_t output[256],int mode,int len,int zparam,int group) {
    #pragma HLS INLINE off
    #pragma HLS DATAFLOW
    hls::stream<req39c>rq("rq39d");hls::stream<rsp39c>rs("rs39d");
    #pragma HLS STREAM variable=rq depth=2
    #pragma HLS STREAM variable=rs depth=2
    issue39d(src,ant,bnt,bm_in,mode,len,zparam,group,rq);pe39c(rq,rs);
    write39d(dst,bm_out,bm_final,output,group,rs);
}

void mlkem_poly_mul256_v39e_true_one_dsp(const coeff_t a[256],const coeff_t b[256],coeff_t output[256]) {
    pair_t ping[128],pong[128],ant[128],bnt[128];residue_t bm[8][64],bm_final[2][64],dummy[8][64];
    #pragma HLS BIND_STORAGE variable=ping type=ram_t2p impl=bram
    #pragma HLS BIND_STORAGE variable=pong type=ram_t2p impl=bram
    #pragma HLS BIND_STORAGE variable=ant type=ram_t2p impl=bram
    #pragma HLS BIND_STORAGE variable=bnt type=ram_t2p impl=bram
    #pragma HLS ARRAY_PARTITION variable=bm complete dim=1
    #pragma HLS ARRAY_PARTITION variable=bm_final complete dim=1
    #pragma HLS ARRAY_PARTITION variable=dummy complete dim=1
    #pragma HLS BIND_STORAGE variable=bm type=ram_1p impl=lutram
    #pragma HLS BIND_STORAGE variable=bm_final type=ram_1p impl=lutram
    #pragma HLS BIND_STORAGE variable=dummy type=ram_1p impl=lutram
    #pragma HLS ALLOCATION function instances=batch39d limit=1
load_a39d:for(int i=0;i<128;++i){
        #pragma HLS PIPELINE II=1
        ping[i]=pack39c(norm39c(a[i]),norm39c(a[i+128]));
    }
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,128,1,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,64,2,0);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,32,4,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,16,8,0);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,8,16,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,4,32,0);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,2,64,0);
save_a39d:for(int i=0;i<128;++i){
        #pragma HLS PIPELINE II=1
        ant[i]=pong[i];
    }
load_b39d:for(int i=0;i<128;++i){
        #pragma HLS PIPELINE II=1
        ping[i]=pack39c(norm39c(b[i]),norm39c(b[i+128]));
    }
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,128,1,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,64,2,0);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,32,4,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,16,8,0);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,8,16,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,4,32,0);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_FNTT39C,2,64,0);
save_b39d:for(int i=0;i<128;++i){
        #pragma HLS PIPELINE II=1
        bnt[i]=pong[i];
    }
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_BM39C,0,0,0);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_BM39C,0,0,1);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_BM39C,0,0,2);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_BM39C,0,0,3);
    batch39d(ping,pong,ant,bnt,bm,dummy,bm_final,output,MODE_BM39C,0,0,4);
pack39d:for(int i=0;i<64;++i){
        #pragma HLS PIPELINE II=1
        ant[i<<1]=pack39c(add39c(bm_final[0][i],bm[1][i]),add39c(bm_final[1][i],bm[5][i]));
        ant[(i<<1)+1]=pack39c(add39c(bm[2][i],bm[3][i]),add39c(bm[6][i],bm[7][i]));
    }
load_i39d:for(int i=0;i<128;++i){
        #pragma HLS PIPELINE II=1
        ping[i]=ant[i];
    }
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_INTT39C,2,127,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_INTT39C,4,63,0);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_INTT39C,8,31,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_INTT39C,16,15,0);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_INTT39C,32,7,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_INTT39C,64,3,0);
    batch39d(ping,pong,ant,bnt,dummy,bm,bm_final,output,MODE_INTT39C,128,1,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_SCALE39C,0,0,0);
    batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_SCALE39C,0,128,0);
}
