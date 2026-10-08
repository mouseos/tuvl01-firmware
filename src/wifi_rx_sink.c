/* SPDX-License-Identifier: MIT. Independent RX-only diagnostic. */
#include "wifi_rx_sink.h"
#include "wifi_net.h"
static unsigned word(const uint8_t *p){return ((unsigned)p[0]<<8)|p[1];}
static uint32_t longword(const uint8_t *p){return ((uint32_t)word(p)<<16)|word(p+2);}
static int same(const uint8_t *a,const uint8_t *b,unsigned n){
    while(n--)if(*a++!=*b++)return 0;
    return 1;
}
static unsigned sum(const uint8_t *p,unsigned n,unsigned s){
    while(n>=2){s+=word(p);p+=2;n-=2;}
    if(n)s+=(unsigned)*p<<8;
    while(s>>16)s=(s&65535)+(s>>16);
    return s;
}
static void add(struct wifi_rx_sink *s,uint32_t *n,uint32_t value){
    if(UINT32_MAX-*n<value){*n=UINT32_MAX;s->overflow=1;}
    else *n+=value;
}
int wifi_rx_sink_receive(struct wifi_rx_sink *s,const uint8_t *f,unsigned n,
                        const uint8_t *mac,const uint8_t *peer,uint32_t tick){
    if(!s || !f || !mac || !peer || n<42 || !same(f,mac,6) ||
       !same(f+6,peer,6) || word(f+12)!=0x0800)return 0;
    const uint8_t *ip=f+14,*u=ip+20;
    unsigned total=word(ip+2);
    if(ip[0]!=0x45 || total<28 || total>1500 || total>n-14 ||
       !ip[8] || ip[9]!=17 || (word(ip+6)&0xbfff) ||
       longword(ip+12)!=WIFI_NET_PEER_IP || longword(ip+16)!=WIFI_NET_IP ||
       sum(ip,20,0)!=65535 || word(u+2)!=WIFI_RX_SINK_PORT)return 0;
    unsigned un=total-20;
    if(word(u+4)!=un || (word(u+6) &&
       sum(u,un,sum(ip+12,8,17+un))!=65535))return 0;
    const uint8_t *body=u+8;unsigned bn=un-8;
    if(bn<12 || body[0]!='T' || body[1]!='W' || body[2]!='R' || body[3]!='1' ||
       longword(body+8)!=bn){add(s,&s->invalid,1);return 1;}
    uint32_t sequence=longword(body+4);
    /* Finite trials: sequence UINT32_MAX is rejected, avoiding wrap ambiguity. */
    if(sequence==UINT32_MAX){add(s,&s->invalid,1);return 1;}
    for(unsigned i=12;i<bn;i++)if(body[i]!=(uint8_t)((i+(sequence%251))%251)){
        add(s,&s->invalid,1);return 1;
    }
    if(sequence<s->next_sequence){add(s,&s->reordered,1);return 1;}
    add(s,&s->missing,sequence-s->next_sequence);s->next_sequence=sequence+1;
    if(s->packets){
        uint32_t gap=tick-s->last_tick;
        if(gap>s->max_gap_ticks)s->max_gap_ticks=gap;
    }else s->first_tick=tick;
    s->last_tick=tick;add(s,&s->packets,1);add(s,&s->bytes,bn);return 1;
}
