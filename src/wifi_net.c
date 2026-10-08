/* SPDX-License-Identifier: MIT. Independent single-peer IPv4 endpoint.
 * RFC826 ARP, RFC792 echo, RFC768 UDP, RFC2131/2132 DHCP fixed allocation.
 * This AP supplies only its own subnet, never an Internet default route. */
#include "wifi_net.h"
static unsigned word(const uint8_t *p){return ((unsigned)p[0]<<8)|p[1];}
static uint32_t longword(const uint8_t *p){return ((uint32_t)word(p)<<16)|word(p+2);}
static void putword(uint8_t *p,unsigned n){p[0]=n>>8;p[1]=n;}
static void putlong(uint8_t *p,uint32_t n){putword(p,n>>16);putword(p+2,n);}
static void copy(uint8_t *d,const uint8_t *s,unsigned n){while(n--)*d++=*s++;}
static int same(const uint8_t *a,const uint8_t *b,unsigned n){while(n--)if(*a++!=*b++)return 0;return 1;}
static unsigned sum(const uint8_t *p,unsigned n,unsigned s){
    while(n>=2){s+=word(p);p+=2;n-=2;}if(n)s+=(unsigned)*p<<8;
    while(s>>16)s=(s&0xffff)+(s>>16);
    return s;
}
static unsigned checksum(const uint8_t *p,unsigned n){return (~sum(p,n,0))&0xffff;}
static unsigned udp_sum(const uint8_t *ip,const uint8_t *udp,unsigned n){
    return sum(udp,n,sum(ip+12,8,17+n));
}
static void ethernet(uint8_t *out,const uint8_t *dst,const uint8_t *mac,unsigned type){
    copy(out,dst,6);copy(out+6,mac,6);putword(out+12,type);
}
static void ipv4(uint8_t *out,uint32_t dst,unsigned proto,unsigned body){
    uint8_t *ip=out+14;for(unsigned i=0;i<20;i++)ip[i]=0;
    ip[0]=0x45;putword(ip+2,20+body);ip[8]=64;ip[9]=proto;
    putlong(ip+12,WIFI_NET_IP);putlong(ip+16,dst);putword(ip+10,checksum(ip,20));
}
static unsigned dhcp(const uint8_t *f,const uint8_t *ip,const uint8_t *u,unsigned n,
                     const uint8_t *mac,const uint8_t *peer,uint8_t *out,unsigned cap){
    static const uint8_t broadcast[6]={255,255,255,255,255,255};
    const uint8_t *b=u+8;unsigned bn=n-8;
    if(bn<240 || b[0]!=1 || b[1]!=1 || b[2]!=6 || b[3] ||
       longword(b+24) || !same(b+28,peer,6) || longword(b+236)!=0x63825363)return 0;
    unsigned type=0,seen=0,ended=0;uint32_t wanted=0,server=0;
    for(unsigned i=240;i<bn;){
        unsigned code=b[i++];if(!code)continue;if(code==255){ended=1;break;}
        if(i>=bn)return 0;
        unsigned len=b[i++];if(len>bn-i)return 0;
        unsigned bit=code==53?1:code==50?2:code==54?4:0;
        if(bit){
            if(seen&bit)return 0;
            seen|=bit;
            if(code==53){if(len!=1)return 0;type=b[i];}
            else {if(len!=4)return 0;if(code==50)wanted=longword(b+i);else server=longword(b+i);}
        }
        if(code==52)return 0; /* option-overloaded fields not supported */
        i+=len;
    }
    if(!ended || (type!=1 && type!=3) || (server && server!=WIFI_NET_IP))return 0;
    unsigned reply=type==1?2:5;
    uint32_t ci=longword(b+12);
    if(type==3){
        uint32_t address=(seen&2)?wanted:ci;
        if(!address)return 0;
        if(address!=WIFI_NET_PEER_IP)reply=6; /* authoritative NAK on our isolated subnet */
    }
    if(cap<342)return 0;
    unsigned broadcast_reply=reply==6 || (!ci && (b[10]&0x80));
    uint32_t dst=broadcast_reply?0xffffffffUL:ci?ci:WIFI_NET_PEER_IP;
    ethernet(out,broadcast_reply?broadcast:peer,mac,0x0800);
    ipv4(out,dst,17,308);uint8_t *ru=out+34,*rb=ru+8;
    for(unsigned i=0;i<308;i++)ru[i]=0;
    putword(ru,67);putword(ru+2,68);putword(ru+4,308);
    rb[0]=2;rb[1]=1;rb[2]=6;copy(rb+4,b+4,4);copy(rb+10,b+10,2);
    if(reply!=6){putlong(rb+12,ci);putlong(rb+16,WIFI_NET_PEER_IP);}
    copy(rb+28,peer,6);putlong(rb+236,0x63825363);
    unsigned k=240;rb[k++]=53;rb[k++]=1;rb[k++]=reply;
    rb[k++]=54;rb[k++]=4;putlong(rb+k,WIFI_NET_IP);k+=4;
    if(reply!=6){
        rb[k++]=51;rb[k++]=4;putlong(rb+k,3600);k+=4;
        rb[k++]=1;rb[k++]=4;putlong(rb+k,0xffffff00UL);k+=4;
    }
    rb[k]=255;unsigned c=(~udp_sum(out+14,ru,308))&0xffff;
    putword(ru+6,c?c:0xffff);
    (void)f;(void)ip;return 342;
}
unsigned wifi_net_reply(const uint8_t *f,unsigned n,const uint8_t *mac,
                        const uint8_t *peer,uint8_t *out,unsigned cap){
    static const uint8_t broadcast[6]={255,255,255,255,255,255};
    if(!f || !mac || !peer || !out || n<14 || !same(f+6,peer,6) ||
       (!same(f,mac,6) && !same(f,broadcast,6)))return 0;
    unsigned et=word(f+12);
    if(et==0x0806){
        if(n<42 || cap<42 || word(f+14)!=1 || word(f+16)!=0x0800 ||
           f[18]!=6 || f[19]!=4 || word(f+20)!=1 ||
           !same(f+22,peer,6) || longword(f+38)!=WIFI_NET_IP)return 0;
        ethernet(out,peer,mac,0x0806);copy(out+14,f+14,28);putword(out+20,2);
        copy(out+22,mac,6);putlong(out+28,WIFI_NET_IP);
        copy(out+32,peer,6);copy(out+38,f+28,4);return 42;
    }
    if(et!=0x0800 || n<34)return 0;
    const uint8_t *ip=f+14;unsigned total=word(ip+2);
    if(ip[0]!=0x45 || total<20 || total>n-14 || !ip[8] ||
       (word(ip+6)&0xbfff) || checksum(ip,20))return 0;
    const uint8_t *body=ip+20;unsigned size=total-20;
    if(ip[9]==17){
        if(size<8 || word(body+4)!=size ||
           (word(body+6) && udp_sum(ip,body,size)!=0xffff))return 0;
        if(word(body)==68 && word(body+2)==67 &&
           (longword(ip+16)==0xffffffffUL || longword(ip+16)==WIFI_NET_IP))
            return dhcp(f,ip,body,size,mac,peer,out,cap);
        if(word(body+2)!=WIFI_NET_UDP_PORT || longword(ip+16)!=WIFI_NET_IP ||
           longword(ip+12)!=WIFI_NET_PEER_IP || total+14>cap)return 0;
        ethernet(out,peer,mac,0x0800);ipv4(out,WIFI_NET_PEER_IP,17,size);
        copy(out+34,body,size);putword(out+34,WIFI_NET_UDP_PORT);putword(out+36,word(body));
        putword(out+40,0);unsigned c=(~udp_sum(out+14,out+34,size))&0xffff;
        putword(out+40,c?c:0xffff);return total+14;
    }
    if(ip[9]!=1 || longword(ip+12)!=WIFI_NET_PEER_IP || longword(ip+16)!=WIFI_NET_IP ||
       size<8 || body[0]!=8 || body[1] || checksum(body,size) || total+14>cap)return 0;
    ethernet(out,peer,mac,0x0800);ipv4(out,WIFI_NET_PEER_IP,1,size);
    copy(out+34,body,size);out[34]=0;putword(out+36,0);
    putword(out+36,checksum(out+34,size));return total+14;
}
unsigned wifi_net_udp(const uint8_t *body,unsigned length,unsigned port,
                      const uint8_t *mac,const uint8_t *peer,uint8_t *out,unsigned cap){
    if(!body || !mac || !peer || !out || !port || port>65535 || length>1472 || cap<42+length)return 0;
    ethernet(out,peer,mac,0x0800);ipv4(out,WIFI_NET_PEER_IP,17,8+length);
    uint8_t *u=out+34;putword(u,port);putword(u+2,port);putword(u+4,8+length);putword(u+6,0);
    copy(u+8,body,length);
    unsigned c=(~udp_sum(out+14,u,8+length))&0xffff;putword(u+6,c?c:0xffff);
    return 42+length;
}
