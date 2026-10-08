#ifndef TUVL_RSN_OS_MEMORY_H
#define TUVL_RSN_OS_MEMORY_H
#include <stddef.h>
void *os_memcpy(void *, const void *, size_t);
void *os_memmove(void *, const void *, size_t);
void *os_memset(void *, int, size_t);
int os_memcmp(const void *, const void *, size_t);
int os_memcmp_const(const void *, const void *, size_t);
void *os_memdup(const void *, size_t);
size_t os_strlen(const char *);
int os_strcmp(const char *, const char *);
int os_strncmp(const char *, const char *, size_t);
char *os_strchr(const char *, int);
char *os_strrchr(const char *, int);
char *os_strstr(const char *, const char *);
char *os_strdup(const char *);
#endif
