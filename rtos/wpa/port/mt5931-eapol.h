/* SPDX-License-Identifier: MIT */
#ifndef TUVL_MT5931_EAPOL_H
#define TUVL_MT5931_EAPOL_H
#include <stddef.h>
#include <stdint.h>
#define TUVL_EAPOL_TC 4u
#define TUVL_EAPOL_PORT 0x2cu
/* AIS0, station0, dedicated security path. Returns SDIO padded length,
 * logical HIF length encoded separately. Inputs/output must not overlap.
 * Does not reserve a credit or perform hardware I/O.
 */
size_t tuvl_mt5931_eapol_tx(uint8_t *,size_t,const uint8_t *,size_t);
#define TUVL_EAPOL_RX_ENCRYPTION_UNKNOWN (-1)
struct tuvl_eapol_rx {
    const uint8_t *frame;
    size_t length;
    unsigned station,rcpi;
    int encryption;
};
/* Logical HIF packet only, excluding SDIO padding/checksum trailer.
 * AIS0/station0, own destination/AP source, Ethernet EAPOL-Key only.
 * No software reorder support: reorder/PAL/TCL/raw/event are rejected.
 * Output view borrows packet lifetime; invalid input clears the view.
 */
int tuvl_mt5931_eapol_rx(const uint8_t *,size_t,const uint8_t own[6],
                         const uint8_t ap[6],struct tuvl_eapol_rx *);
#endif
