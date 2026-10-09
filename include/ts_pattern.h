/* SPDX-License-Identifier: MIT */
#ifndef TS_PATTERN_H
#define TS_PATTERN_H
#include <stdint.h>
/* A repeatable batch of 32 payload-only PID 0x1ffe packets. No program/video. */
unsigned ts_pattern_fill(uint8_t *out,unsigned capacity);
/* Varying payload for DMA loopback integrity testing, same PID/batch layout. */
unsigned ts_pattern_dma_fill(uint8_t *out,unsigned capacity);
#endif
