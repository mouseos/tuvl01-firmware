/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
static uint8_t spcr,e8,f8,e7;
static uint16_t mux,ior,dr,pr;
static uint32_t dma[2];
static unsigned operations,fail_at,stuck_high,ssl_low,changed_chip,pad_reads;
static char end[128];
uint8_t *pin_mock8(uint32_t a){assert(a==0xffff8800U);return &spcr;}
uint16_t *pin_mock16(uint32_t a){
    if(a==0xfffe386cU)return &mux;
    if(a==0xfffe3872U)return &ior;
    if(a==0xfffe3876U)return &dr;
    assert(a==0xfffe387aU);pr=0xf0;
    if(mux==0x2220 && (ior&0x10)){
        pad_reads++;
        if(!stuck_high && !(dr&0x10))pr&=~0x10;
        if(ssl_low)pr&=~0x20;
    }
    return &pr;
}
uint32_t *pin_mock32(uint32_t a){assert(a==0xfffe100cU || a==0xfffe101cU);return &dma[a==0xfffe101cU];}
uint32_t board_time_counts(void){assert(0);return 0;}
void uart_puts(const char *s){if(strstr(s,"PIN selftest end status="))snprintf(end,sizeof end,"%s",s);}
void uart_hex(uint32_t v){(void)v;}
int tuner_read_register(unsigned b,unsigned r,uint8_t *v){
    assert((b==0x62 && (r==0xe8 || r==0xf8)) || (b==0x61 && r==0xe7));
    if(++operations==fail_at)return -1;
    *v=r==0xe8?e8:r==0xf8?f8:e7;
    if(changed_chip && operations==4)*v^=1;
    return 0;
}
int tuner_write_register(unsigned b,unsigned r,uint8_t v){(void)b;(void)r;(void)v;assert(0);return -1;}
static void reset(void){
    spcr=8;e8=2;f8=1;e7=0;mux=0x2222;ior=0x5a02;dr=0xab12;pr=0xf0;
    dma[0]=dma[1]=operations=fail_at=stuck_high=ssl_low=changed_chip=pad_reads=0;end[0]=0;
}
static void restored(void){assert(mux==0x2222 && ior==0x5a02 && dr==0xab12);}
int main(void){
    reset();tuner_pin_gpio_selftest();restored();assert(pad_reads==32 && strstr(end,"verified-restored"));
    for(unsigned n=1;n<=6;n++){reset();fail_at=n;tuner_pin_gpio_selftest();restored();
        assert(strstr(end,n<=3?"i2c-failed-before-change":"chip-state-unconfirmed"));}
    reset();stuck_high=1;tuner_pin_gpio_selftest();restored();assert(strstr(end,"readback-mismatch-restored"));
    reset();ssl_low=1;tuner_pin_gpio_selftest();restored();assert(pad_reads==2 && strstr(end,"readback-mismatch-restored"));
    reset();changed_chip=1;tuner_pin_gpio_selftest();restored();assert(strstr(end,"chip-state-unconfirmed"));
    reset();e8=0;tuner_pin_gpio_selftest();restored();assert(!pad_reads && strstr(end,"unexpected-tuner-state"));
    reset();dma[1]=1;tuner_pin_gpio_selftest();restored();assert(!operations);
    puts("GPIO selftest: unchanged chip, pad mismatch, SSL abort, I/O failures and restoration passed");
}
