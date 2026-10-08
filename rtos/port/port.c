/* SPDX-License-Identifier: MIT */
#include "FreeRTOS.h"
#include "task.h"
#include "board.h"
extern void vPortStartFirstTask(void);
StackType_t *pxPortInitialiseStack(StackType_t *top,TaskFunction_t entry,void *arg) {
    /* Mirrors portasm.S: GBR,MACH,MACL,R0..R14,PR,PC,SR. */
    *top--=0; /* SR: integer tasks, interrupts unmasked. */
    *top--=(uint32_t)entry;
    *top--=(uint32_t)fault; /* Task returning is a fault. */
    for(int r=14;r>=0;r--) *top--=r==4?(uint32_t)arg:0;
    *top--=0; /* MACL */
    *top--=0; /* MACH */
    *top=0;   /* GBR */
    return top;
}
BaseType_t xPortStartScheduler(void) {
    R8(0xfffe0418)&=(uint8_t)~4; /* STBCR7 MSTP72: CMT */
    (void)R8(0xfffe0418);
    R16(0xfffec000)&=(uint16_t)~1;
    R16(0xfffec002)=0x40; /* interrupt enable, Pclk/8 */
    R16(0xfffec004)=0;
    R16(0xfffec006)=BOARD_PCLK_HZ/8/configTICK_RATE_HZ-1;
    R16(0xfffe0c08)=(R16(0xfffe0c08)&~0xf0)|0x10; /* CMI0=level1 */
    R16(0xfffec000)|=1;
    vPortStartFirstTask();
    return 0;
}
void vPortEndScheduler(void) { fault(); }
void vPortYield(void) {
    unsigned sr;
    __asm__ volatile("stc sr,%0" : "=r"(sr));
    port_mask(0xf0); /* TRAPA itself does not raise the interrupt mask. */
    __asm__ volatile("trapa #33" ::: "memory");
    port_mask(sr&0xf0);
}
void port_tick(void) {
    R16(0xfffec002)&=(uint16_t)~0x80;
    if (xTaskIncrementTick()) vTaskSwitchContext();
}
