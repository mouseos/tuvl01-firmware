/* SPDX-License-Identifier: MIT */
#ifndef TUVL_SUPPLICANT_SEND_H
#define TUVL_SUPPLICANT_SEND_H
#include <stddef.h>
#include <stdint.h>
struct tuvl_send_transport {
    uint8_t own[6],ap[6];
    void *ctx;
    /* Single radio/session owner only. Reserve the real TC4 credit and
     * complete/copy the FIFO payload before returning. Zero means accepted
     * submission, not firmware TXdone, RF ACK or WPA completion. */
    int (*submit)(void *,unsigned port,unsigned tc,const uint8_t *,size_t);
    unsigned busy;
    uint32_t packet[640]; /* aligned, max2062B Ethernet + HIF + block padding */
};
/* Signature matches tuvl_rsn_driver.send. Workspace is wiped after submission.
 * The callback must not retain pointers or reconfigure this transport. */
int tuvl_supplicant_send(void *,const uint8_t *,size_t);
#endif
