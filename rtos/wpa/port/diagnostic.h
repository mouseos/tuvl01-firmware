#ifndef TUVL_RSN_DIAGNOSTIC_H
#define TUVL_RSN_DIAGNOSTIC_H
#include <stddef.h>
#include <stdint.h>
#include <stdarg.h>
typedef void (*tuvl_rsn_log_fn)(void *, int, const char *);
typedef void (*tuvl_rsn_panic_fn)(void *);
/* Single owner; install before wpa_sm_init. Logger strings valid only in call.
 * No key hexdumps, floating point formatting, or automatic recovery assumed.
 */
void tuvl_rsn_set_log(tuvl_rsn_log_fn fn, void *ctx, int minimum_level);
void tuvl_rsn_set_panic(tuvl_rsn_panic_fn fn, void *ctx);
uint32_t tuvl_rsn_log_dropped(void);
uint32_t tuvl_rsn_log_truncated(void);
int os_snprintf(char *,size_t,const char *,...);
void wpa_msg(void *,int,const char *,...);
#endif
