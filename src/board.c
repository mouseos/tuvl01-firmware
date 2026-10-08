/* SPDX-License-Identifier: MIT */
#include "board.h"
#define SCIF 0xfffe8800UL
void board_init(void) {
    R16(0xfffe080c)=0; /* IBCR: software context, no automatic register banks. */
    R16(0xfffe0010)=0x3004; /* Matched stock loader write, no PLL assumption. */
    R8(0xfffe040c)&=(uint8_t)~0x40;
    (void)R8(0xfffe040c);
    R16(SCIF+8)=0;
    R16(SCIF+0x18)=6;
    R16(SCIF+0x10)&=(uint16_t)~0x91;
    R16(SCIF+0x24)&=(uint16_t)~1;
    R16(SCIF)=0;
    R16(SCIF+0x28)=0;
    R8(SCIF+4)=9;
    R16(SCIF+0x18)=0x30;
    R16(0xfffe382a)=(R16(0xfffe382a)&~0x3300)|0x2200;
    /* > one nominal baud period before TE/RE; no console suppression flag. */
    for (volatile unsigned n=0;n<20000;n++) __asm__ volatile("nop");
    R16(SCIF+8)=0x30;
}
static void putc_uart(char c) {
    unsigned timeout=1000000;
    while (!(R16(SCIF+0x10)&0x20) && --timeout) {}
    if (!timeout) return;
    R8(SCIF+0xc)=(uint8_t)c;
    R16(SCIF+0x10)&=(uint16_t)~0x60;
}
void uart_puts(const char *s) { while (*s) { if (*s=='\n') putc_uart('\r'); putc_uart(*s++); } }
void uart_hex(uint32_t n) { const char *h="0123456789abcdef"; for(int i=28;i>=0;i-=4) putc_uart(h[(n>>i)&15]); }
int uart_getc(void) {
    if (!(R16(SCIF+0x10)&2)) return -1;
    int c=R8(SCIF+0x14);
    R16(SCIF+0x10)&=(uint16_t)~2;
    return c;
}
void fault(void) { __asm__ volatile("mov #0xf0,r0\n extu.b r0,r0\n ldc r0,sr" ::: "r0","memory"); uart_puts("FAULT: recovery requires reset\n"); for (;;) {} }
