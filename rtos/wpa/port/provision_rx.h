/* SPDX-License-Identifier: MIT */
#ifndef TUVL_PROVISION_RX_H
#define TUVL_PROVISION_RX_H
#include "owner.h"
#include "provision.h"
#define TUVL_PROVISION_TIMEOUT_MS 2000u
enum tuvl_provision_rx_state {
    TUVL_RX_IDLE,TUVL_RX_RECEIVING,TUVL_RX_APPLYING,
    TUVL_RX_ACCEPTED,TUVL_RX_REJECTED,TUVL_RX_TIMEOUT
};
struct tuvl_provision_rx {
    u8 packet[TUVL_PROVISION_BYTES];
    struct tuvl_rsn_owner *owner;
    size_t used;
    u32 started;
    enum tuvl_provision_rx_state state;
};
/* Initially zeroed; same radio/task owner. Feed accepts bytes only while
 * receiving and never returns surplus bytes for console dispatch. Terminal
 * state stays latched; caller must drain/resynchronize UART before reset.
 * Caller must wipe its own chunk buffer. No data or credential echo.
 */
int tuvl_provision_rx_begin(struct tuvl_provision_rx *,struct tuvl_rsn_owner *,u32);
enum tuvl_provision_rx_state tuvl_provision_rx_feed(struct tuvl_provision_rx *,
    const u8 *,size_t,u32);
enum tuvl_provision_rx_state tuvl_provision_rx_poll(struct tuvl_provision_rx *,u32);
int tuvl_provision_rx_reset(struct tuvl_provision_rx *);
#endif
