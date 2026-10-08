/* SPDX-License-Identifier: MIT */
#ifndef BOARD_H
#define BOARD_H
#include <stdint.h>
#include <stddef.h>
#define R8(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define R16(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define R32(a) (*(volatile uint32_t *)(uintptr_t)(a))
/* Nominal only: stock FRQCR and X1 photograph; not a measured clock. */
#define BOARD_PCLK_HZ 36000000UL
#define BOARD_VECTOR_COUNT 512U
#define BOARD_SDHI0_VECTOR 281U
#define BOARD_SDHI1_VECTOR 282U
#define APP_BASE 0x1c000000UL
#define APP_LIMIT 0x1c100000UL
#define APP_FLASH 0x00010000UL
#define FLASH_LIMIT 0x00800000UL
void board_init(void);
void uart_puts(const char *s);
void uart_hex(uint32_t n);
int uart_getc(void);
int flash_read(uint32_t address, void *dst, uint32_t size);
void fault(void) __attribute__((noreturn));
#endif
