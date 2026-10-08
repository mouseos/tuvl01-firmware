/* Independent freestanding byte/string operations. */
#include "os-memory.h"
#include <stdint.h>
void *os_malloc(size_t);

void *os_memcpy(void *dst, const void *src, size_t n)
{
    unsigned char *d=dst;
    const unsigned char *s=src;
    size_t i;
    for(i=0;i<n;i++) d[i]=s[i];
    return dst;
}
void *os_memmove(void *dst, const void *src, size_t n)
{
    unsigned char *d=dst;
    const unsigned char *s=src;
    if((uintptr_t)d>(uintptr_t)s) {
        while(n) { n--; d[n]=s[n]; }
    } else os_memcpy(dst,src,n);
    return dst;
}
void *os_memset(void *dst, int c, size_t n)
{
    unsigned char *d=dst;
    size_t i;
    for(i=0;i<n;i++) d[i]=(unsigned char)c;
    return dst;
}
int os_memcmp(const void *a, const void *b, size_t n)
{
    const unsigned char *x=a,*y=b;
    size_t i;
    for(i=0;i<n;i++) if(x[i]!=y[i]) return (int)x[i]-(int)y[i];
    return 0;
}
int os_memcmp_const(const void *a, const void *b, size_t n)
{
    const volatile unsigned char *x=a,*y=b;
    unsigned char diff=0;
    size_t i;
    for(i=0;i<n;i++) diff|=x[i]^y[i];
    return diff;
}
void *os_memdup(const void *src, size_t n)
{
    void *out;
    if(!src && n) return NULL;
    out=os_malloc(n);
    if(out) os_memcpy(out,src,n);
    return out;
}
size_t os_strlen(const char *s)
{
    size_t n=0;
    while(s[n]) n++;
    return n;
}
int os_strcmp(const char *a, const char *b)
{
    const unsigned char *x=(const unsigned char *)a,*y=(const unsigned char *)b;
    while(*x && *x==*y) { x++; y++; }
    return (int)*x-(int)*y;
}
int os_strncmp(const char *a, const char *b, size_t n)
{
    const unsigned char *x=(const unsigned char *)a,*y=(const unsigned char *)b;
    size_t i;
    for(i=0;i<n;i++) {
        if(x[i]!=y[i]) return (int)x[i]-(int)y[i];
        if(!x[i]) return 0;
    }
    return 0;
}
char *os_strchr(const char *s, int c)
{
    unsigned char target=(unsigned char)c;
    do {
        if((unsigned char)*s==target) return (char *)s;
    } while(*s++);
    return NULL;
}
char *os_strrchr(const char *s, int c)
{
    char *found=NULL;
    unsigned char target=(unsigned char)c;
    do {
        if((unsigned char)*s==target) found=(char *)s;
    } while(*s++);
    return found;
}
char *os_strstr(const char *s, const char *needle)
{
    size_t n=os_strlen(needle);
    if(!n) return (char *)s;
    for(;*s;s++) if(!os_strncmp(s,needle,n)) return (char *)s;
    return NULL;
}
char *os_strdup(const char *s)
{
    size_t n=os_strlen(s);
    if(n==SIZE_MAX) return NULL;
    return os_memdup(s,n+1);
}
