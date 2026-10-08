/* SPDX-License-Identifier: MIT */
#include "wifi_link.h"
int wifi_link_decode(const uint8_t *p,unsigned length,uint8_t sequence,
                     struct wifi_link_quality *quality){
    if((length!=14 && length!=20) || (unsigned)(p[0]|((unsigned)p[1]<<8))!=length ||
       (p[2]|((unsigned)p[3]<<8))!=1 || p[4]!=5 || p[5]!=sequence)return 0;
    unsigned count=length==20?2:1,ready_known=length==20;
    if(ready_known && (p[13]>1 || p[19]>1))return 0;
    quality->count=count;quality->ready_known=ready_known;
    for(unsigned n=0;n<count;n++){
        const uint8_t *body=p+8+n*6;
        quality->entry[n].rssi=body[0]<128?body[0]:(int)body[0]-256;
        quality->entry[n].quality_raw=body[1];
        quality->entry[n].speed_raw=body[2]|((unsigned)body[3]<<8);
        quality->entry[n].busy_raw=body[4];
        quality->entry[n].ready=ready_known?body[5]:0;
    }
    return 1;
}
