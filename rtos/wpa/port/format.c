/* Independent wrapper; nanoprintf source is retained unmodified under 0BSD. */
#include "diagnostic.h"
#define NANOPRINTF_IMPLEMENTATION
#define NANOPRINTF_USE_FIELD_WIDTH_FORMAT_SPECIFIERS 1
#define NANOPRINTF_USE_PRECISION_FORMAT_SPECIFIERS 1
#define NANOPRINTF_USE_FLOAT_FORMAT_SPECIFIERS 0
#define NANOPRINTF_USE_LARGE_FORMAT_SPECIFIERS 1
#define NANOPRINTF_USE_SMALL_FORMAT_SPECIFIERS 1
#define NANOPRINTF_USE_BINARY_FORMAT_SPECIFIERS 0
#define NANOPRINTF_USE_WRITEBACK_FORMAT_SPECIFIERS 0
#define NANOPRINTF_USE_ALT_FORM_FLAG 1
#include "nanoprintf.h"
int vsnprintf(char *out,size_t n,const char *fmt,va_list ap)
{
    return npf_vsnprintf(out,n,fmt,ap);
}
int os_snprintf(char *out,size_t n,const char *fmt,...)
{
    va_list ap;
    int res;
    va_start(ap,fmt);
    res=npf_vsnprintf(out,n,fmt,ap);
    va_end(ap);
    return res;
}
