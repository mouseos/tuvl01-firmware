#include "diagnostic.h"
int vsnprintf(char *,size_t,const char *,va_list);
static tuvl_rsn_log_fn log_fn;
static void *log_ctx;
static int threshold=3, active;
static uint32_t dropped,truncated;
static tuvl_rsn_panic_fn panic_fn;
static void *panic_ctx;
static void increment(uint32_t *counter)
{
    if(*counter!=UINT32_MAX) (*counter)++;
}
void tuvl_rsn_set_log(tuvl_rsn_log_fn fn,void *ctx,int minimum_level)
{
    log_fn=fn; log_ctx=ctx; threshold=minimum_level;
}
void tuvl_rsn_set_panic(tuvl_rsn_panic_fn fn,void *ctx)
{
    panic_fn=fn; panic_ctx=ctx;
}
uint32_t tuvl_rsn_log_dropped(void) { return dropped; }
uint32_t tuvl_rsn_log_truncated(void) { return truncated; }
void wpa_msg(void *ctx,int level,const char *fmt,...)
{
    char text[256];
    int res;
    va_list ap;
    (void)ctx;
    if(level<threshold) return;
    if(!log_fn || !fmt || active) { increment(&dropped); return; }
    active=1;
    va_start(ap,fmt);
    res=vsnprintf(text,sizeof(text),fmt,ap);
    va_end(ap);
    if(res<0) increment(&dropped);
    else {
        if((size_t)res>=sizeof(text)) increment(&truncated);
        log_fn(log_ctx,level,text);
    }
    active=0;
}
/* A platform hook may reset or transfer to recovery. If it returns, stop.
 * Never return to the failed caller or silently report success.
 */
_Noreturn void abort(void)
{
    if(panic_fn) panic_fn(panic_ctx);
    for(;;) { }
}
