/* SPDX-License-Identifier: MIT; independent public HIF ABI serialization. */
#include "mt5931-eapol.h"
size_t tuvl_mt5931_eapol_tx(uint8_t *out,size_t cap,const uint8_t *frame,size_t n)
{
    size_t logical,padded,i;
    uintptr_t a,b;
    if(!out || !frame || n<18 || n>2062 || (frame[0]&1) ||
       (frame[6]&1) || frame[12]!=0x88 || frame[13]!=0x8e ||
       (frame[14]!=1 && frame[14]!=2) || frame[15]!=3 ||
       ((size_t)frame[16]<<8 | frame[17])!=n-18) return 0;
    logical=16+n;padded=(logical+3u)&~(size_t)3;
    /* Match current SH SDIO byte/block transfer lengths, not Ethernet padding. */
    if(padded>512) padded=(padded+511u)&~(size_t)511;
    if(cap<padded) return 0;
    a=(uintptr_t)out;b=(uintptr_t)frame;
    if(a<=b ? b-a<padded : a-b<n) return 0;
    for(i=0;i<padded;i++) out[i]=0;
    out[0]=(uint8_t)logical;out[1]=(uint8_t)(logical>>8);
    out[2]=14;out[3]=TUVL_EAPOL_TC<<2;out[4]=14;
    out[5]=0x40; /* AIS0, 1X flag, Ethernet format. */
    out[10]=0;out[11]=0x20; /* station0, burst end; no TXdone/PHY ACK claim. */
    for(i=0;i<n;i++) out[16+i]=frame[i];
    return padded;
}
int tuvl_mt5931_eapol_rx(const uint8_t *p,size_t n,const uint8_t own[6],
                         const uint8_t ap[6],struct tuvl_eapol_rx *view)
{
    size_t offset,length,i;
    const uint8_t *f;
    if(!view) return 0;
    *view=(struct tuvl_eapol_rx){0};
    view->encryption=TUVL_EAPOL_RX_ENCRYPTION_UNKNOWN;
    if(!p || !own || !ap || n<30 || (p[0]|((size_t)p[1]<<8))!=n ||
       (p[2]&3) || p[5] || (p[7]&0x80) || p[8]) return 0;
    offset=12+(p[4]&3);
    if(n<offset+18 || n-offset>2062) return 0;
    length=n-offset;f=p+offset;
    for(i=0;i<6;i++) if(f[i]!=own[i] || f[6+i]!=ap[i]) return 0;
    if(f[12]!=0x88 || f[13]!=0x8e || (f[14]!=1 && f[14]!=2) ||
       f[15]!=3 || ((size_t)f[16]<<8 | f[17])!=length-18) return 0;
    view->frame=f;view->length=length;view->station=p[8];view->rcpi=p[9];
    return 1;
}
