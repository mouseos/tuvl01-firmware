/* SPDX-License-Identifier: MIT */
#ifndef WIFI_RAW_TX_H
#define WIFI_RAW_TX_H
#include <stdint.h>
/* Native From-DS data MPDU in network1/TC1/station0 HIF; no encryption.
 * Input/output must be disjoint. Returns complete padded transfer size.
 * Zero means invalid input/capacity; output is unchanged on rejection. */
unsigned wifi_raw_tx_pack(const uint8_t *ethernet,unsigned length,const uint8_t *bssid,unsigned sequence,uint8_t *out,unsigned capacity);
/* QoS Data, TID0/normal ACK, still TC1; requires negotiated WMM. */
unsigned wifi_raw_qos_tx_pack(const uint8_t *ethernet,unsigned length,const uint8_t *bssid,unsigned sequence,uint8_t *out,unsigned capacity);
/* Only matched (TID,TC) pairs (0,1), (4,2), (6,3) are accepted. */
unsigned wifi_raw_qos_class_tx_pack(const uint8_t *ethernet,unsigned length,const uint8_t *bssid,unsigned sequence,uint8_t *out,unsigned capacity,unsigned tid,unsigned tc);
#endif
