/* SPDX-License-Identifier: MIT */
#ifndef WIFI_CTL_H
#define WIFI_CTL_H
#include <stdint.h>
/* Client-neutral Wi-Fi control service, UDP port 4200 (see docs/protocol.md).
 * Nothing here is specific to a particular player or operating system. */
#define WIFI_CTL_PORT 4200
#define WIFI_CTL_VERSION 1
#define WIFI_CTL_REVISION 167
#define WIFI_CTL_CAP_STREAM 1U /* START/STOP of the TS stream */
/* Handler for datagrams addressed to the device: wifi_net_service signature.
 * Returns the reply length, or zero for no reply. Port 4201 (echo) only
 * refreshes the client-liveness watchdog. */
unsigned wifi_ctl_service(unsigned port,const uint8_t *body,unsigned length,
                          uint8_t *reply,unsigned capacity);
/* UART task only. Returns a pending virtual UART command ('B' start,
 * 'E' stop) or -1. A stream started by a control client is stopped when the
 * peer sends nothing for `timeout` ticks. */
int wifi_ctl_poll(unsigned now,unsigned timeout);
#endif
