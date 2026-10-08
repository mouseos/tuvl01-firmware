/* SPDX-License-Identifier: MIT */
#include "wifi_raw_tx.h"
#include <stddef.h>
static unsigned pack(const uint8_t *eth,unsigned length,const uint8_t *bssid,unsigned sequence,uint8_t *out,unsigned capacity,unsigned qos,unsigned tid,unsigned tc){
    if(!eth || !bssid || !out || length<14 || length>1514 || (eth[0]&1) || (eth[6]&1) || (bssid[0]&1))return 0;
    if(qos && !((tid==0 && tc==1) || (tid==4 && tc==2) || (tid==6 && tc==3)))return 0;
    unsigned mac=24+2*qos;
    unsigned logical=16+mac+8+length-14;
    unsigned padded=(logical+3)&~3U;if(padded>512)padded=(padded+511)&~511U;
    if(padded>capacity)return 0;
    uintptr_t e=(uintptr_t)eth,o=(uintptr_t)out,m=(uintptr_t)bssid;
    if((e<=o && o-e<length) || (o<e && e-o<padded) ||
       (m<=o && o-m<6) || (o<m && m-o<padded))return 0;
    for(unsigned n=0;n<padded;n++)out[n]=0;
    out[0]=logical;out[1]=(logical>>8)|(tid<<4);out[2]=(mac+22)/2;out[3]=tc<<2;
    out[4]=mac;out[5]=0x90;out[11]=0x20;
    uint8_t *frame=out+16;frame[0]=qos?0x88:0x08;frame[1]=0x02;
    for(unsigned n=0;n<6;n++){frame[4+n]=eth[n];frame[10+n]=bssid[n];frame[16+n]=eth[6+n];}
    unsigned control=(sequence&0xfffU)<<4;frame[22]=control;frame[23]=control>>8;
    if(qos)frame[24]=tid;
    frame[mac]=frame[mac+1]=0xaa;frame[mac+2]=3;
    frame[mac+6]=eth[12];frame[mac+7]=eth[13];
    for(unsigned n=14;n<length;n++)frame[mac+8+n-14]=eth[n];
    return padded;
}

unsigned wifi_raw_tx_pack(const uint8_t *e,unsigned n,const uint8_t *m,unsigned seq,uint8_t *o,unsigned cap){return pack(e,n,m,seq,o,cap,0,0,1);}
unsigned wifi_raw_qos_tx_pack(const uint8_t *e,unsigned n,const uint8_t *m,unsigned seq,uint8_t *o,unsigned cap){return pack(e,n,m,seq,o,cap,1,0,1);}
unsigned wifi_raw_qos_class_tx_pack(const uint8_t *e,unsigned n,const uint8_t *m,unsigned seq,uint8_t *o,unsigned cap,unsigned tid,unsigned tc){return pack(e,n,m,seq,o,cap,1,tid,tc);}
