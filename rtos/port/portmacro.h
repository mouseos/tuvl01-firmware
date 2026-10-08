/* SPDX-License-Identifier: MIT; integer-only SH-2A GNU ABI port. */
#ifndef PORTMACRO_H
#define PORTMACRO_H
#include <stdint.h>
typedef uint32_t StackType_t;
typedef long BaseType_t;
typedef unsigned long UBaseType_t;
typedef uint32_t TickType_t;
#define portSTACK_TYPE uint32_t
#define portBASE_TYPE long
#define portMAX_DELAY UINT32_MAX
#define portTICK_TYPE_IS_ATOMIC 1
#define portSTACK_GROWTH (-1)
#define portBYTE_ALIGNMENT 8
#define portTICK_PERIOD_MS ((TickType_t)1000/configTICK_RATE_HZ)
#define portCRITICAL_NESTING_IN_TCB 1
void vPortYield(void);
void vTaskEnterCritical(void);
void vTaskExitCritical(void);
static inline void port_mask(unsigned mask) {
    unsigned sr;
    __asm__ volatile("stc sr,%0" : "=r"(sr));
    sr=(sr&~0xf0U)|mask;
    __asm__ volatile("ldc %0,sr" :: "r"(sr) : "memory");
}
/* CMT is the only enabled peripheral IRQ, at level 1. No nesting is
 * supported by save_context/restore_context: future scheduler-aware IRQs
 * must use the same level or explicitly mask nesting on entry. Critical
 * sections use level 15; hardware IRQ entry itself masks its accepted level. */
#define portDISABLE_INTERRUPTS() port_mask(0xf0)
#define portENABLE_INTERRUPTS() port_mask(0)
#define portENTER_CRITICAL() vTaskEnterCritical()
#define portEXIT_CRITICAL() vTaskExitCritical()
#define portYIELD() vPortYield()
#define portNOP() __asm__ volatile("nop")
#define portTASK_FUNCTION_PROTO(f,p) void f(void *p)
#define portTASK_FUNCTION(f,p) void f(void *p)
#endif
