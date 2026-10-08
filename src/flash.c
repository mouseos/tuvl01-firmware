/* SPDX-License-Identifier: MIT; SH726A manual section 17. */
#include "board.h"
#include "image.h"
#define S 0xffff8000UL
static int wait_spi(uint8_t mask) {
    unsigned n=200000;
    while (!(R8(S+3)&mask) && --n) {}
    return n?0:-1;
}
static int byte(uint8_t out) {
    if(wait_spi(0x20)) return -1;
    R8(S+4)=out;
    if(wait_spi(0x80)) return -1;
    return R8(S+4);
}
static void end(void) { R8(S)=8; }
static void begin(void) {
    R8(S)=8;
    R8(S+0x20)=0xc0;
    R8(S+0x20)=0;
    R8(S)=0x48;
}
void flash_init(void) {
    R8(0xfffe0410)&=(uint8_t)~2;
    (void)R8(0xfffe0410);
    R16(0xfffe38ae)=(R16(0xfffe38ae)&~0x3333)|0x1111;
    R8(S)=8;R8(S+1)=0;R8(S+2)=0;R8(S+8)=0;
    R8(S+0xa)=35; /* nominal Bclk 72MHz /72 = 1MHz */
    R8(S+0xb)=0x20; /* byte SPDR access */
    R16(S+0x10)=0x0780; /* 8 bit, mode0, SSL00 held between bytes */
}
static int address(uint8_t cmd,uint32_t a) {
    begin();
    if(byte(cmd)<0 || byte(a>>16)<0 || byte(a>>8)<0 || byte(a)<0) {end();return -1;}
    return 0;
}
uint32_t flash_id(void) {
    begin();int c=byte(0x9f),a=byte(0xff),b=byte(0xff),d=byte(0xff);end();
    return c<0||a<0||b<0||d<0?0:((uint32_t)a<<16)|(b<<8)|d;
}
int flash_read(uint32_t a,void *dst,uint32_t n) {
    if(a>FLASH_LIMIT || n>FLASH_LIMIT-a) return -1;
    if(address(3,a)) return -1;
    uint8_t *p=dst;
    while(n--) {int v=byte(0xff);if(v<0){end();return -1;}*p++=v;}
    end();return 0;
}
int flash_status(void) {
    begin();int c=byte(5),r=byte(0xff);end();return c<0?-1:r;
}
static int wren(void) {
    begin();int r=byte(6);end();if(r<0)return -1;
    r=flash_status();return r>=0 && (r&2)?0:-1;
}
int flash_erase(uint32_t a) {
    if(a<APP_FLASH || a>=APP_FLASH+APP_CAPACITY+4096 || (a&4095) || flash_id()!=0x014017 || wren()) return -1;
    if(address(0x20,a))return -1;
    end();return 0;
}
int flash_program(uint32_t a,const void *data,uint32_t n) {
    if(!n || n>256 || a<APP_FLASH || a>=APP_FLASH+APP_CAPACITY+4096 || n>APP_FLASH+APP_CAPACITY+4096-a || (a&255)+n>256 || wren())return -1;
    if(address(2,a))return -1;
    const uint8_t *p=data;
    while(n--) if(byte(*p++)<0){end();return -1;}
    end();return 0;
}
