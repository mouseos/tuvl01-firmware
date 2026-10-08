/* SPDX-License-Identifier: MIT */
#ifndef WIFI_STATUS_H
#define WIFI_STATUS_H
#include <stdint.h>
struct wifi_status { uint32_t interrupt,tx0,tx1,rx_lengths,mailbox0,mailbox1; };
/* MT5931 fixed-port 88-byte status, with one reported RX length per port.
 * Returns one on valid input. Failure leaves output unchanged. */
int wifi_status_decode(const uint8_t *data,unsigned length,struct wifi_status *out);
#endif
