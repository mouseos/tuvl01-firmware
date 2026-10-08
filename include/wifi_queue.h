/* SPDX-License-Identifier: MIT */
#ifndef WIFI_QUEUE_H
#define WIFI_QUEUE_H
#include <stdint.h>
/* Independent non-QoS network1 AP command: 0 public LE, 1 stock values
 * LE, 2 stock values BE. This describes requested bytes, not HW application. */
unsigned wifi_queue_pack(uint8_t *out,unsigned capacity,unsigned mode);
#endif
