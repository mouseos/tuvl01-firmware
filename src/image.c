/* SPDX-License-Identifier: MIT; CRC32/ISO-HDLC; corruption check, not authentication. */
#include "image.h"
uint32_t crc32_update(uint32_t c,const void *d,uint32_t n) {
    const uint8_t *p=d;
    while(n--) { c^=*p++;for(unsigned b=0;b<8;b++) c=(c>>1)^((0-(c&1))&0xedb88320UL); }
    return c;
}
uint32_t crc32(const void *d,uint32_t n) {return ~crc32_update(UINT32_MAX,d,n);}
int image_valid(const Image *h) {
    return h->magic==0x5455564c && h->version==1 && h->address==APP_BASE && h->entry==APP_BASE && h->reserved==0 && h->size && h->size<=APP_CAPACITY && h->header_crc==crc32(h,28);
}
