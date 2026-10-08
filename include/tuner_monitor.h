/* SPDX-License-Identifier: MIT */
#ifndef TUNER_MONITOR_H
#define TUNER_MONITOR_H
#include <stdint.h>
/* 1 frame lock without reference error flags, 0 unlocked, -1 error. */
int tuner_frame_state(uint8_t status95,uint8_t status97);
void tuner_monitor(void);
void tuner_fec_snapshot(void);
void tuner_quality(void);
#endif
