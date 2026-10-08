/* SPDX-License-Identifier: MIT. Exercise the production driver with MMIO
 * storage. SYSCFG expectations come from SH726A manual 27.3.1/27.4.1(3).
 * This does not emulate USB signaling or clock behavior. */
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#define BOARD_H
static uint16_t usb_regs[128],pgcr,phcr;
static uint8_t stbcr6;
static unsigned watch,saw_host;
static unsigned pin_reads;
static volatile uint16_t *reg16(uintptr_t address) {
    if(address>=0xffffc000UL && address<0xffffc100UL) {
        if(watch && address==0xffffc000UL) {
            unsigned value=usb_regs[0];
            assert(!(value&0x20)); /* DRPD must remain zero in this sequence. */
            assert((value&0x401)==0x401); /* preserve SCKE and USBE */
            if(value&0x40) { assert(!(value&0x10));saw_host=1; }
        }
        return &usb_regs[(address-0xffffc000UL)/2];
    }
    if(address==0xfffe38ceUL)return &pgcr;
    if(address==0xfffe38eeUL)return &phcr;
    if(address==0xfffe38daUL){
        static uint16_t pins=6;
        assert(!(pgcr&0x33));pin_reads++;return &pins;
    }
    assert(0 && "Unexpected MMIO access");return 0;
}
static volatile uint8_t *reg8(uintptr_t address) {
    assert(address==0xfffe0414UL);return &stbcr6;
}
#define R16(a) (*reg16(a))
#define R8(a) (*reg8(a))
void uart_puts(const char *s){(void)s;}
void uart_hex(uint32_t n){(void)n;}
#include "../src/usb.c"
int usb_request(unsigned t,unsigned r,unsigned v,unsigned i,unsigned l,unsigned char *p){
    (void)t;(void)r;(void)v;(void)i;(void)l;(void)p;return -1;
}
int usb_out(const unsigned char *p,unsigned n){(void)p;(void)n;return -1;}
void usb_idle(void){}
int main(void) {
    usb_init();
    usb_regs[0x40/2]=0x80;usb_poll();
    assert(usb_regs[0]==0x411 && attached);
    configured=1;remain=64;receiving=1;need_zlp=1;
    usb_regs[0x40/2]=0;watch=1;usb_poll();watch=0;
    assert(saw_host && usb_regs[0]==0x401);
    assert(!attached && !configured && !remain && !receiving && !need_zlp);
    saw_host=0;watch=1;usb_poll();watch=0;
    assert(!saw_host); /* a stable disconnected cable causes no repeated pulse */
    usb_regs[0x40/2]=0x80;usb_poll();
    assert(usb_regs[0]==0x411 && attached && !configured);
    pgcr=0x5511;usb_pin_debug();
    assert(pin_reads==1 && pgcr==0x5511 && usb_regs[0]==0x411);
    configured=1;usb_pin_debug();assert(pin_reads==1);
    configured=0;setup_count=1;usb_pin_debug();assert(pin_reads==1);
    setup_count=0;usb_regs[0x50/2]=1;usb_pin_debug();assert(pin_reads==1);
    return 0;
}
