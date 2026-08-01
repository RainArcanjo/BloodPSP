// Minimal POSIX compatibility expected by the historical JFBuild layer.
// PSP has no host sysconf(); report the native page size and 32 MiB RAM.
#include <unistd.h>

long sysconf(int name)
{
#ifdef _SC_PAGE_SIZE
    if (name == _SC_PAGE_SIZE)
        return 4096;
#endif
#ifdef _SC_PAGESIZE
    if (name == _SC_PAGESIZE)
        return 4096;
#endif
#ifdef _SC_PHYS_PAGES
    if (name == _SC_PHYS_PAGES)
        return 8192;
#endif
    return 1;
}
