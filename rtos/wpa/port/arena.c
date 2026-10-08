/* Independent single-owner RSN arena. No FreeRTOS heap dependency.
 * Caller must serialize all access; no interrupt/other-task callers allowed.
 */
#include <stddef.h>
#include <stdint.h>

#define ARENA_BYTES 65536u
#define ALIGNMENT 8u
typedef struct { size_t span; size_t used; } block;
static union { uint64_t alignment; unsigned char bytes[ARENA_BYTES]; } arena;
static int initialized;

static block *at(size_t offset) { return (block *)(arena.bytes + offset); }
static void wipe(unsigned char *p, size_t n)
{
    volatile unsigned char *v = p;
    while (n--) *v++ = 0;
}

static block *find(void *p)
{
    size_t offset = 0;
    if (!initialized || !p) return NULL;
    while (offset < ARENA_BYTES) {
        block *b = at(offset);
        if ((unsigned char *)b + sizeof(*b) == p && b->used) return b;
        offset += b->span;
    }
    return NULL;
}

void *os_malloc(size_t n)
{
    size_t offset = 0, need;
    if (!n || n > ARENA_BYTES - sizeof(block) - (ALIGNMENT - 1)) return NULL;
    need = sizeof(block) + ((n + ALIGNMENT - 1) & ~(size_t)(ALIGNMENT - 1));
    if (!initialized) {
        at(0)->span = ARENA_BYTES;
        at(0)->used = 0;
        initialized = 1;
    }
    while (offset < ARENA_BYTES) {
        block *b = at(offset);
        if (!b->used && b->span >= need) {
            if (b->span - need >= sizeof(block) + ALIGNMENT) {
                block *next = at(offset + need);
                next->span = b->span - need;
                next->used = 0;
                b->span = need;
            }
            b->used = n;
            return (unsigned char *)b + sizeof(*b);
        }
        offset += b->span;
    }
    return NULL;
}

void os_free(void *p)
{
    block *b = find(p);
    size_t offset = 0;
    if (!b) return;
    wipe(p, b->span - sizeof(*b));
    b->used = 0;
    while (offset < ARENA_BYTES) {
        block *cur = at(offset);
        if (!cur->used && offset + cur->span < ARENA_BYTES) {
            block *next = at(offset + cur->span);
            if (!next->used) {
                size_t span = next->span;
                wipe((unsigned char *)next, sizeof(*next));
                cur->span += span;
                continue;
            }
        }
        offset += cur->span;
    }
}

void *os_zalloc(size_t n)
{
    void *p = os_malloc(n);
    if (p) wipe(p,n);
    return p;
}

void *os_realloc(void *p, size_t n)
{
    block *old;
    unsigned char *out;
    size_t i, count;
    if (!p) return os_malloc(n);
    old = find(p);
    if (!old) return NULL;
    if (!n) { os_free(p); return NULL; }
    out = os_malloc(n);
    if (!out) return NULL;
    count = old->used < n ? old->used : n;
    for (i = 0; i < count; i++) out[i] = ((unsigned char *)p)[i];
    os_free(p);
    return out;
}
