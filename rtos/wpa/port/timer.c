/* Independent bounded timeout adapter; caller owns serialization. */
#include "utils/includes.h"
#include <limits.h>
#include "utils/os.h"
#include "utils/eloop.h"
#include "timer.h"

#define TIMER_CAPACITY 32u
struct timeout {
    uint64_t deadline;
    eloop_timeout_handler handler;
    void *ctx;
    void *user;
};
static struct timeout queue[TIMER_CAPACITY];
static size_t count;
static uint32_t last_tick;
static uint64_t elapsed;
static int started, dispatching;

int tuvl_rsn_clock_start(uint32_t tick)
{
    if (started) return -1;
    last_tick = tick;
    elapsed = 0;
    started = 1;
    return 0;
}

uint64_t tuvl_rsn_elapsed_ms(void) { return elapsed; }

int eloop_register_timeout(unsigned int secs, unsigned int usecs,
                           eloop_timeout_handler handler,
                           void *ctx, void *user)
{
    uint64_t delay, deadline;
    size_t i;
    if (!started || !handler || count == TIMER_CAPACITY) return -1;
    /* Round fractional milliseconds upward: never fire early. */
    delay = (uint64_t)secs * 1000u + ((uint64_t)usecs + 999u) / 1000u;
    if (UINT64_MAX - elapsed < delay) return -1;
    deadline = elapsed + delay;
    i = count;
    while (i && queue[i-1].deadline > deadline) {
        queue[i] = queue[i-1];
        i--;
    }
    queue[i].deadline = deadline;
    queue[i].handler = handler;
    queue[i].ctx = ctx;
    queue[i].user = user;
    count++;
    return 0;
}

int eloop_cancel_timeout(eloop_timeout_handler handler, void *ctx, void *user)
{
    size_t src, dst = 0;
    int removed = 0;
    for (src = 0; src < count; src++) {
        struct timeout t = queue[src];
        if (t.handler == handler && (ctx == ELOOP_ALL_CTX || ctx == t.ctx) &&
            (user == ELOOP_ALL_CTX || user == t.user)) removed++;
        else queue[dst++] = t;
    }
    count = dst;
    return removed;
}

int tuvl_rsn_poll(uint32_t tick)
{
    size_t i;
    unsigned int fired = 0;
    uint32_t delta;
    if (!started || dispatching) return -1;
    delta = tick - last_tick;
    if (UINT64_MAX - elapsed < delta) return -1;
    elapsed += delta;
    last_tick = tick;
    dispatching = 1;
    /* Bound even a callback that continually schedules a zero-delay timer. */
    while (count && queue[0].deadline <= elapsed && fired < TIMER_CAPACITY) {
        struct timeout t = queue[0];
        count--;
        for (i = 0; i < count; i++) queue[i] = queue[i+1];
        fired++;
        t.handler(t.ctx, t.user);
    }
    dispatching = 0;
    return (int)fired;
}

int os_get_reltime(struct os_reltime *t)
{
    uint64_t sec = elapsed / 1000u;
    if (!started || !t || sec > LONG_MAX) return -1;
    t->sec = (os_time_t)sec;
    t->usec = (os_time_t)((elapsed % 1000u) * 1000u);
    return 0;
}
