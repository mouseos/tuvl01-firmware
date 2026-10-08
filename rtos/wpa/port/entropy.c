#include "entropy.h"
static unsigned char pool[512];
static size_t position, available;

void tuvl_rsn_entropy_clear(void)
{
    volatile unsigned char *v = pool;
    size_t i;
    for (i=0;i<sizeof(pool);i++) v[i]=0;
    position=available=0;
}
size_t tuvl_rsn_entropy_remaining(void) { return available; }

int tuvl_rsn_entropy_supply(const unsigned char *bytes, size_t n)
{
    size_t i;
    if (!bytes || !n || n>sizeof(pool) || available) return -1;
    tuvl_rsn_entropy_clear();
    for (i=0;i<n;i++) pool[i]=bytes[i];
    available=n;
    return 0;
}

int os_get_random(unsigned char *out, size_t n)
{
    size_t i;
    volatile unsigned char *v=pool;
    if ((!out && n) || n>available) return -1;
    for (i=0;i<n;i++) {
        out[i]=pool[position+i];
        v[position+i]=0;
    }
    position+=n;
    available-=n;
    if (!available) position=0;
    return 0;
}
int random_get_bytes(void *out, size_t n) { return os_get_random(out,n); }
