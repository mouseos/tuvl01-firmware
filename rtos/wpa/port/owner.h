/* SPDX-License-Identifier: MIT */
#ifndef TUVL_RSN_OWNER_H
#define TUVL_RSN_OWNER_H
#include "session.h"
struct tuvl_rsn_target {
    u8 own[6],ap[6],ssid[32],rsn[257];
    size_t ssid_length,rsn_length;
    unsigned channel;
};
struct tuvl_rsn_owner {
    struct tuvl_rsn_target target;
    struct tuvl_rsn_driver driver;
    struct tuvl_rsn_session *session;
    unsigned prepared,busy,associated,entropy_owned;
};
/* Initially zeroed object; one serialized radio/task owner. Target must come
 * from validated selected beacon. Driver callbacks must not reenter control.
 * Prepare and provision do not report association or hardware key success. */
int tuvl_rsn_owner_prepare(struct tuvl_rsn_owner *,const struct tuvl_rsn_target *,
    const struct tuvl_rsn_driver *);
int tuvl_rsn_owner_provision(struct tuvl_rsn_owner *,u8 *,size_t);
int tuvl_rsn_owner_assoc_ie(struct tuvl_rsn_owner *,u8 *,size_t *);
/* Call only after radio owner verifies association/AIS activation conditions. */
int tuvl_rsn_owner_associated(struct tuvl_rsn_owner *);
/* Logical HIF RX packet, no SDIO padding/trailer; validate before supplicant. */
int tuvl_rsn_owner_rx(struct tuvl_rsn_owner *,const u8 *,size_t);
int tuvl_rsn_owner_poll(struct tuvl_rsn_owner *,u32 milliseconds);
enum wpa_states tuvl_rsn_owner_state(const struct tuvl_rsn_owner *);
void tuvl_rsn_owner_close(struct tuvl_rsn_owner *);
#endif
