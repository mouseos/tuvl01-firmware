/* SPDX-License-Identifier: MIT */
#ifndef TUNER_PROFILE_H
#define TUNER_PROFILE_H
#include <stdint.h>
/* Fixed 32-byte, CRC-protected protocol. No arbitrary register addresses. */
int tuner_profile_valid(const uint8_t *data);
void tuner_profile_receive(void);
/* Applies a validated profile (tune sequence only; no UART frame). Services the Wi-Fi radio while waiting.
 * Returns TUNER_PROFILE_OK, or one of the negative codes. Completion is not broadcast lock. */
enum {TUNER_PROFILE_OK=0,TUNER_PROFILE_REJECTED=-1,TUNER_PROFILE_NOT_CALIBRATED=-2,TUNER_PROFILE_I2C_FAILED=-3,TUNER_PROFILE_TIMEOUT=-4};
int tuner_profile_apply(const uint8_t *profile);
/* Waits up to timeout_ms for stable broadcast frame lock (servicing the Wi-Fi radio).
 * Returns 1 when locked, 0 on timeout. A TS stream cannot start before this. */
int tuner_lock_wait(unsigned timeout_ms);
void tuner_profile_switch(void);
#endif
