/* SPDX-License-Identifier: MIT */
#include "wifi_ts_tx.h"
#include "wifi_net.h"
unsigned wifi_ts_tx_pack_forwarding(const uint8_t *data,unsigned count,unsigned sequence,
    unsigned index,unsigned flags,const uint8_t *mac,const uint8_t *peer,
    uint8_t *out,unsigned capacity,unsigned more_data){
    if(!data || !mac || !peer || !out || !count || count>14 || more_data>1)return 0;
    /* Ethernet/IP/UDP=42 bytes, HIF=16, TTS1=16. Preflight the whole
     * transfer before touching output. A zero DWORD must fit after frames. */
    unsigned total=0,left=count;
    while(left){unsigned n=left>7?7:left;total+=(74+n*188+3)&~3U;left-=n;}
    unsigned transfer=(total+4+511)&~511U;
    if(transfer>capacity)return 0;
    unsigned offset=0;
    while(count){
        unsigned n=count>7?7:count;
        uint8_t *body=out+offset+16+42;
        /* Payload bytes are overwritten below. Clear only the HIF fields,
         * frame alignment and trailing terminator/padding. */
        for(unsigned i=0;i<16;i++)out[offset+i]=0;
        body[0]='T';body[1]='T';body[2]='S';body[3]='1';
        for(unsigned b=0;b<4;b++){
            body[4+b]=sequence>>(24-b*8);body[8+b]=index>>(24-b*8);
            body[12+b]=flags>>(24-b*8);
        }
        for(unsigned i=0;i<n*188;i++)body[16+i]=data[i];
        unsigned length=wifi_net_udp(body,16+n*188,4202,mac,peer,
            out+offset+16,transfer-offset-16);
        if(!length)return 0;
        unsigned logical=16+length;
        out[offset]=logical;out[offset+1]=logical>>8;
        out[offset+2]=14;out[offset+3]=1<<2;
        out[offset+4]=14;out[offset+5]=0x10;
        /* All frames target the same station and TC1 queue. Mark only its
         * final frame as burst end, including the one-frame case. */
        /* Linux protocol: MORE_DATA=3 when another same-peer frame remains.
         * PS session stays zero; final frame retains NON_PS + burst end. */
        out[offset+11]=count<=7?0x20:more_data?3:0;
        unsigned aligned=(logical+3)&~3U;
        for(unsigned i=logical;i<aligned;i++)out[offset+i]=0;
        offset+=aligned;
        data+=n*188;count-=n;index+=n;++sequence;flags=0;
    }
    for(unsigned i=offset;i<transfer;i++)out[i]=0;
    return transfer;
}

unsigned wifi_ts_tx_pack(const uint8_t *data,unsigned count,unsigned sequence,
    unsigned index,unsigned flags,const uint8_t *mac,const uint8_t *peer,
    uint8_t *out,unsigned capacity){
    return wifi_ts_tx_pack_forwarding(data,count,sequence,index,flags,mac,peer,out,capacity,0);
}
