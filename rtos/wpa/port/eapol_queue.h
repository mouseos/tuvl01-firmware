/* SPDX-License-Identifier: MIT */
#ifndef TUVL_EAPOL_QUEUE_H
#define TUVL_EAPOL_QUEUE_H
#include <stdint.h>
#include <stddef.h>
#define TUVL_EAPOL_QUEUE_DEPTH 4u
#define TUVL_EAPOL_RX_MAX 2077u
struct tuvl_eapol_queue {
    uint8_t packet[TUVL_EAPOL_QUEUE_DEPTH][TUVL_EAPOL_RX_MAX];
    size_t length[TUVL_EAPOL_QUEUE_DEPTH];
    unsigned head,count,failed;
};
/* Single SDIO owner. The source may be reused immediately after copying.
 * Overflow latches failure instead of silently dropping handshake traffic. */
int tuvl_eapol_queue_push(struct tuvl_eapol_queue *,const uint8_t *,size_t);
const uint8_t *tuvl_eapol_queue_front(const struct tuvl_eapol_queue *,size_t *);
void tuvl_eapol_queue_pop(struct tuvl_eapol_queue *);
void tuvl_eapol_queue_clear(struct tuvl_eapol_queue *);
#endif
