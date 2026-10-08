/* SPDX-License-Identifier: MIT */
#ifndef WIFI_TX_FEEDBACK_H
#define WIFI_TX_FEEDBACK_H
#include <stdint.h>
struct wifi_tx_feedback {
    uint32_t sequence[128],status[256];
    uint8_t occupied[128],next;
    uint32_t requested,completed,pending,skipped,unmatched,cancelled;
};
int wifi_tx_feedback_reserve(struct wifi_tx_feedback *,uint32_t,uint8_t *);
int wifi_tx_feedback_complete(struct wifi_tx_feedback *,uint8_t,uint8_t,uint32_t *);
void wifi_tx_feedback_cancel(struct wifi_tx_feedback *,uint8_t);
#endif
