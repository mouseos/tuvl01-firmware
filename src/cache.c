/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "FreeRTOS.h"
#include "cache.h"
extern uint32_t board_cache_instruction_write(unsigned enabled);
int instruction_cache_set(unsigned enabled){
    /* Manual 9.2.1: CCR1 writes execute uncached and are followed by readback.
     * Manual 30.1: 3Cxxxxxx aliases the application's 1Cxxxxxx RAM uncached.
     * Operand cache remains disabled; do not silently discard dirty data. */
    uint32_t before=R32(0xfffc1000UL);
    if(enabled>1 || (before&1U))return -1;
    unsigned sr;__asm__ volatile("stc sr,%0":"=r"(sr));port_mask(0xf0);
    uintptr_t target=(uintptr_t)board_cache_instruction_write|0x20000000UL;
    uint32_t after=((uint32_t (*)(unsigned))target)(enabled);
    port_mask(sr&0xf0);
    return ((after&0x100U)!=enabled*0x100U || (after&1U))?-1:0;
}
void instruction_cache_toggle(void){
    uint32_t before=R32(0xfffc1000UL);
    int result=instruction_cache_set(!(before&0x100U));
    uart_puts("ICACHE CCR1 before=");uart_hex(before);
    uart_puts(" after=");uart_hex(R32(0xfffc1000UL));
    uart_puts(" FRQCR=");uart_hex(R16(0xfffe0010UL));uart_puts("\n");
    uart_puts(result?"ICACHE end status=failed\n":"ICACHE end status=ready\n");
}
