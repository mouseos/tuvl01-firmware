/* SPDX-License-Identifier: MIT */
#ifndef TUNER_PROFILE_H
#define TUNER_PROFILE_H
#include <stdint.h>
/* Fixed 32-byte, CRC-protected protocol. No arbitrary register addresses. */
int tuner_profile_valid(const uint8_t *data);
void tuner_profile_receive(void);
void tuner_profile_switch(void);
#endif
