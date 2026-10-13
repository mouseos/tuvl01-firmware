/* SPDX-License-Identifier: MIT */
#ifndef TUNER_SERVE_H
#define TUNER_SERVE_H
/* Channel tuned at bring-up; clients select others over Wi-Fi (TUNE). */
#ifndef TUVL01_DEFAULT_CHANNEL
#define TUVL01_DEFAULT_CHANNEL 14U
#endif
/* Brings the whole receiver up without a PC: tuner initialization, UHF tune,
 * TS path, Wi-Fi radio and the access point, in the proven order. Afterwards a
 * client controls everything over Wi-Fi (README.md). UART task only.
 * Prints "SERVE end status=ready" or "SERVE end status=<failed step>". */
void tuner_serve(void);
#endif
