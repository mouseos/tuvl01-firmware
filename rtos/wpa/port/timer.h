#ifndef TUVL_RSN_TIMER_H
#define TUVL_RSN_TIMER_H
#include <stdint.h>
/* Single task owner, 1kHz uint32 tick source. Poll at least once per wrap.
 * This is an elapsed clock, not a real-time clock or an entropy source.
 */
int tuvl_rsn_clock_start(uint32_t tick);
int tuvl_rsn_poll(uint32_t tick);
uint64_t tuvl_rsn_elapsed_ms(void);
#endif
