/* SPDX-License-Identifier: MIT. Independent bounded protocol serialization. */
#include "wifi_ht.h"
int wifi_ht_parse(const uint8_t *p,unsigned length,struct wifi_ht_peer *out){
    struct wifi_ht_peer parsed={0};
    if(!out || (!p && length))return 0;
    for(unsigned pos=0;pos<length;){
        if(length-pos<2 || p[pos+1]>length-pos-2)return 0;
        unsigned id=p[pos],size=p[pos+1];const uint8_t *b=p+pos+2;
        if(id==45){
            if(parsed.present || size!=26)return 0;
            parsed.present=1;parsed.capability=b[0]|((uint16_t)b[1]<<8);
            parsed.ampdu=b[2];parsed.mcs=b[3];
            if(parsed.ampdu&0xe0)return 0;
        }else if(id==221 && size>=4 && !b[0] && b[1]==0x50 && b[2]==0xf2 && b[3]==2){
            if(parsed.qos || size!=7 || b[4]!=0 || b[5]!=1)return 0;
            parsed.qos=1;
        }
        pos+=size+2;
    }
    *out=parsed;return 1;
}
int wifi_ht_active(const struct wifi_ht_peer *p){return p && p->present && p->qos && p->mcs;}
unsigned wifi_ht_ies(uint8_t *out,unsigned capacity,unsigned channel,unsigned ht,unsigned qos){
    if(!out || channel<1 || channel>13 || ht>1 || qos>1)return 0;
    unsigned size=ht*52+qos*26;
    if(capacity<size)return 0;
    unsigned n=0;
    if(ht){
        for(unsigned i=0;i<52;i++)out[i]=0;
        out[0]=45;out[1]=26;out[2]=0x0c; /* SMPS disabled, 20MHz/long GI */
        out[5]=0xff; /* RX MCS0..7, single stream */
        out[15]=65;out[17]=1; /* RX highest rate65; TX MCS defined, same set */
        out[28]=61;out[29]=22;out[30]=channel;
        out[32]=3; /* Mixed protection; no secondary channel, no greenfield */
        out[36]=1; /* Basic MCS0 */
        n=52;
    }
    if(qos){
        static const uint8_t wmm[26]={221,24,0,0x50,0xf2,2,1,1,0,0,
            3,0xa4,0,0,0x27,0xa4,0,0,0x42,0x43,94,0,0x62,0x32,47,0};
        for(unsigned i=0;i<26;i++)out[n+i]=wmm[i];
        n+=26;
    }
    return n;
}
int wifi_ht_station(uint8_t *out,unsigned length,const struct wifi_ht_peer *peer){
    if(!out || length!=48 || !peer)return 0;
    out[26]=peer->qos!=0;out[27]=0; /* UAPSD deliberately not advertised */
    for(unsigned i=29;i<=40;i++)out[i]=0;
    if(wifi_ht_active(peer)){
        out[21]|=8;out[29]=peer->mcs;out[31]=peer->ampdu;
        /* Only negotiated20MHz long-GI/one-stream capabilities are used. */
        out[32]=peer->capability&0x0c;
    }
    return 1;
}
unsigned wifi_ht_queues(uint8_t *out,unsigned capacity){
    static const uint16_t ac[4][4]={{15,1023,0,3},{15,1023,0,7},{7,15,94,2},{3,7,47,2}};
    if(!out || capacity<52)return 0;
    for(unsigned i=0;i<52;i++)out[i]=0;
    for(unsigned q=0;q<4;q++)for(unsigned f=0;f<4;f++){
        unsigned offset=8+q*10+f*2;out[offset]=ac[q][f];out[offset+1]=ac[q][f]>>8;
    }
    out[48]=1;out[49]=1;return 52;
}

unsigned wifi_beacon_pack(uint8_t *out,unsigned capacity,const uint8_t *ies,unsigned length){
    if(!out || !ies || !length || length>255)return 0;
    unsigned padded=(16+length+3)&~3U;
    if(capacity<padded)return 0;
    for(unsigned n=0;n<padded;n++)out[n]=0;
    out[8]=out[9]=out[12]=1;out[13]=4;out[14]=length;
    for(unsigned n=0;n<length;n++)out[16+n]=ies[n];
    return padded;
}
