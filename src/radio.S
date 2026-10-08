/* SPDX-License-Identifier: MIT. Descriptor and placement only.
 * The included MT5931 vendor binary has separate, unconfirmed license terms. */
    #include "radio-config.h"
    .section .radio,"a"
    .balign 4
    .global _wifi_radio_descriptor,_wifi_radio_bytes,_wifi_radio_end
_wifi_radio_descriptor:
    .long 0x4d543331,RADIO_LENGTH,RADIO_CRC,0xff900000
_wifi_radio_bytes:
    .incbin RADIO_FILE
_wifi_radio_end:
