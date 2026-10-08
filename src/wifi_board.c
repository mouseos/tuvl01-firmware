/* SPDX-License-Identifier: MIT */
#include "wifi_board.h"
/* TUVL01 board settings: CCK/DSSS, reserved, OFDM, HT20, HT40, 5GHz.
 * Signed values use the MT5931 protocol's 0.5 dBm units. */
const uint8_t wifi_board_tx_power[40]={
    38,38,0,0,32,32,32,32,32,32,
    32,32,32,32,32,32,28,28,28,28,28,28,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
};
