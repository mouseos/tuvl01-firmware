/* SPDX-License-Identifier: MIT. Descriptor and placement only.
 * The included MT5931 vendor binary has separate, unconfirmed license terms. */
    .section .radio,"a"
    .balign 4
    .global _wifi_radio_descriptor,_wifi_radio_bytes,_wifi_radio_end
_wifi_radio_descriptor:
    .long 0x4d543331,0x21580,0x1061bd8e,0xff900000
_wifi_radio_bytes:
    .incbin "firmware/mt5931.bin"
_wifi_radio_end:
