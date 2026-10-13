/* SPDX-License-Identifier: MIT */
#define BOARD_H
#include <stdint.h>
uint8_t *pin_mock8(uint32_t);
uint16_t *pin_mock16(uint32_t);
uint32_t *pin_mock32(uint32_t);
#define R8(a) (*pin_mock8(a))
#define R16(a) (*pin_mock16(a))
#define R32(a) (*pin_mock32(a))
void uart_puts(const char *);
void uart_hex(uint32_t);
