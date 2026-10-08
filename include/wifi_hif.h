/* SPDX-License-Identifier: MIT */
#ifndef WIFI_HIF_H
#define WIFI_HIF_H
#include <stdint.h>
/* View borrows the RX buffer; callers must consume/copy before the next RX.
 * Returns zero for non-Ethernet, malformed or other-network packets. */
struct wifi_ethernet_view {
    const uint8_t *frame;
    unsigned length;
    uint16_t ethertype;
    uint8_t station,rcpi;
};
int wifi_hif_ethernet(const uint8_t *packet,unsigned length,unsigned network,
                      struct wifi_ethernet_view *view);
#endif
