/* SPDX-License-Identifier: MIT */
#ifndef TS_BENCHMARK_PROTOCOL_H
#define TS_BENCHMARK_PROTOCOL_H
#include <stdint.h>
/* Returns 1..300 seconds, or zero for an invalid 12-byte request. */
unsigned ts_benchmark_seconds(const uint8_t *packet,unsigned length);
#endif
