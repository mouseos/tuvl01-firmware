/* SPDX-License-Identifier: MIT */
#include "provision.h"
static void wipe(void *p,size_t n)
{ volatile uint8_t *v=p;while(n--)*v++=0; }
static uint32_t crc32(const uint8_t *p,size_t n)
{
    uint32_t c=0xffffffffu;
    while(n--){c^=*p++;for(unsigned i=0;i<8;i++)c=(c>>1)^((0u-(c&1u))&0xedb88320u);}
    return ~c;
}
int tuvl_provision_consume(uint8_t *p,size_t n,
    int (*apply)(void *,const struct tuvl_provision *),void *ctx)
{
    struct tuvl_provision c={0};unsigned ap=0,entropy=0;int result=-1;
    if(!p || n!=TUVL_PROVISION_BYTES || !apply)goto done;
    if(p[0]!='T' || p[1]!='P' || p[2]!='M' || p[3]!='K' || p[4]!=1 ||
       !p[5] || p[5]>13 || !p[6] || p[6]>32 || p[7] || p[14] || p[15] ||
       (p[8]&1))goto done;
    if(crc32(p,144)!=((uint32_t)p[144]|((uint32_t)p[145]<<8)|
                      ((uint32_t)p[146]<<16)|((uint32_t)p[147]<<24)))goto done;
    for(unsigned i=0;i<6;i++)ap|=p[8+i];
    for(unsigned i=0;i<64;i++)entropy|=p[80+i];
    if(!ap || !entropy)goto done;
    for(unsigned i=p[6];i<32;i++)if(p[16+i])goto done;
    c.channel=p[5];c.ssid_length=p[6];
    for(unsigned i=0;i<6;i++)c.ap[i]=p[8+i];
    for(unsigned i=0;i<32;i++){c.ssid[i]=p[16+i];c.pmk[i]=p[48+i];}
    for(unsigned i=0;i<64;i++)c.entropy[i]=p[80+i];
    if(!apply(ctx,&c))result=0;
done:
    wipe(&c,sizeof c);
    if(p && n<=TUVL_PROVISION_BYTES)wipe(p,n);
    return result;
}
