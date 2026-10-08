/* SPDX-License-Identifier: MIT */
#ifndef TIME_COUNTS_H
#define TIME_COUNTS_H
#include <stdint.h>
/* Task context only; tick IRQ latency must stay below one compare period. */
uint32_t board_time_counts(void);
#endif
