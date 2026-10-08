#ifndef TUVL_RSN_ENTROPY_H
#define TUVL_RSN_ENTROPY_H
#include <stddef.h>
/* Single owner. Caller must supply fresh cryptographically random bytes over
 * a trusted provisioning path; this API cannot measure their quality.
 * Never provision from ticks, identifiers, test fixtures or stored/reused data.
 * Refill only an empty pool. No persistent seed, PRNG or fallback exists.
 */
int tuvl_rsn_entropy_supply(const unsigned char *bytes, size_t n);
void tuvl_rsn_entropy_clear(void);
size_t tuvl_rsn_entropy_remaining(void);
int os_get_random(unsigned char *out, size_t n);
int random_get_bytes(void *out, size_t n);
#endif
