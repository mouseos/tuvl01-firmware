/* SPDX-License-Identifier: MIT */
#ifndef TS_PATTERN_H
#define TS_PATTERN_H
#include <stdint.h>
/* A repeatable batch of 32 payload-only PID 0x1ffe packets. No program/video. */
unsigned ts_pattern_fill(uint8_t *out,unsigned capacity);
#endif
