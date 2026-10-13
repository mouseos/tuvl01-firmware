/* SPDX-License-Identifier: MIT */
#ifndef WIFI_CTL_H
#define WIFI_CTL_H
#include <stdint.h>
/* Client-neutral Wi-Fi control service, UDP port 4200 (see README.md).
 * Nothing here is specific to a particular player or operating system. */
#define WIFI_CTL_PORT 4200
#define WIFI_CTL_VERSION 1
#define WIFI_CTL_REVISION 168
#define WIFI_CTL_CAP_STREAM 1U /* START/STOP of the TS stream */
#define WIFI_CTL_CAP_TUNE 2U   /* TUNE of UHF channels 13..52 */
/* Handler for datagrams addressed to the device: wifi_net_service signature.
 * Returns the reply length, or zero for no reply. Port 4201 (echo) only
 * refreshes the client-liveness watchdog. */
unsigned wifi_ctl_service(unsigned port,const uint8_t *body,unsigned length,
                          uint8_t *reply,unsigned capacity);
/* UART task only. Returns a pending virtual UART command ('B' start,
 * 'E' stop) or -1. A stream started by a control client is stopped when the
 * peer sends nothing for `timeout` ticks. */
int wifi_ctl_poll(unsigned now,unsigned timeout);
/* UART task only. Returns 1 once when a TUNE request is waiting and fills the
 * channel (13..52) and mode (0 full segment, 1 one segment); the caller stops
 * any stream, tunes, then reports the outcome with wifi_ctl_tune_done(). */
int wifi_ctl_take_tune(unsigned *channel,unsigned *partial);
void wifi_ctl_tune_done(int ok);
/* Nonzero once a control client has ever contacted the device (the tuner is then
 * known to be initialized, so background lock polling is safe). */
int wifi_ctl_client_seen(void);
/* Nonzero while a control client is talking to the device: a 4200/4201 datagram arrived within
 * `window` ticks of `now`. Used for the "connected" LED; Wi-Fi association is not enough because
 * a station that leaves is not noticed. */
int wifi_ctl_client_alive(unsigned now,unsigned window);
/* Broadcast lock as last observed: 0 unlocked, 1 locked, 255 unknown. */
void wifi_ctl_set_lock(unsigned lock);
#endif
