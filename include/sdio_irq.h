/* SPDX-License-Identifier: MIT */
#ifndef SDIO_IRQ_H
#define SDIO_IRQ_H
#include <stdint.h>
int sdio_irq_set(unsigned enabled);
unsigned sdio_irq_enabled(void);
/* Completion bits remain in hardware until the transaction owner consumes
 * them. ISR masks sources; task waits re-arm only their current phase. */
int sdio_irq_wait(unsigned info1,unsigned info2,uint32_t ticks);
void sdio_irq_handler(void);
unsigned sdio_irq_counter(unsigned index);
#endif
