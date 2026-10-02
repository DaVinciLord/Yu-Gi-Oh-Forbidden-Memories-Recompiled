/* The pthread and POSIX clock calls the native code makes, on Windows, in
 * place of MinGW's winpthreads. That library brings OpenProcess,
 * SuspendThread, GetThreadContext, SetThreadContext, SetSystemTime and
 * SetProcessAffinityMask into the executable's imports for pthread_cancel and
 * the like, which the game never calls; antivirus models read that import
 * list as an injector's. Only what the game uses is here, with winpthreads'
 * behaviour: nanosleep sleeps whole milliseconds and returns at once for less
 * than one. */
#ifdef _WIN32
#include <windows.h>
#include <process.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>

/* A pthread_t is one of these. The thread and its joiner (or detach) each
 * hold a reference; the last to let go frees it. */
typedef struct {
    void *(*function)(void *);
    void *argument;
    void *result;
    HANDLE handle;
    volatile LONG references;
} Thread;

static void release(Thread *thread)
{
    if (InterlockedDecrement(&thread->references) == 0) free(thread);
}

static unsigned __stdcall start(void *pointer)
{
    Thread *thread = pointer;
    thread->result = thread->function(thread->argument);
    release(thread);
    return 0;
}

int pthread_create(pthread_t *out, const pthread_attr_t *attributes, void *(*function)(void *), void *argument)
{
    Thread *thread = calloc(1, sizeof(*thread));
    (void)attributes;
    if (!thread) return EAGAIN;
    thread->function = function;
    thread->argument = argument;
    thread->references = 2;
    thread->handle = (HANDLE)_beginthreadex(NULL, 0, start, thread, 0, NULL);
    if (!thread->handle) {
        free(thread);
        return EAGAIN;
    }
    *out = (pthread_t)thread;
    return 0;
}

int pthread_join(pthread_t handle, void **result)
{
    Thread *thread = (Thread *)handle;
    WaitForSingleObject(thread->handle, INFINITE);
    CloseHandle(thread->handle);
    if (result) *result = thread->result;
    release(thread);
    return 0;
}

int pthread_detach(pthread_t handle)
{
    Thread *thread = (Thread *)handle;
    CloseHandle(thread->handle);
    release(thread);
    return 0;
}

/* The mutex is an SRW lock in the pthread_mutex_t's own word, which
 * PTHREAD_MUTEX_INITIALIZER sets to -1: the first lock clears it to an
 * unlocked SRW lock. An SRW lock's word is never -1. */
int pthread_mutex_lock(pthread_mutex_t *mutex)
{
    if (*mutex == PTHREAD_MUTEX_INITIALIZER) InterlockedCompareExchangePointer((void **)mutex, NULL, (void *)-1);
    AcquireSRWLockExclusive((SRWLOCK *)mutex);
    return 0;
}

int pthread_mutex_unlock(pthread_mutex_t *mutex)
{
    ReleaseSRWLockExclusive((SRWLOCK *)mutex);
    return 0;
}

int __cdecl clock_gettime64(clockid_t clock, struct _timespec64 *now)
{
    if (clock == CLOCK_MONOTONIC) {
        static LARGE_INTEGER frequency;
        LARGE_INTEGER count;
        if (!frequency.QuadPart) QueryPerformanceFrequency(&frequency);
        QueryPerformanceCounter(&count);
        now->tv_sec = count.QuadPart / frequency.QuadPart;
        now->tv_nsec = (long)(count.QuadPart % frequency.QuadPart * 1000000000 / frequency.QuadPart);
        return 0;
    }
    if (clock == CLOCK_REALTIME) {
        FILETIME file_time;
        ULARGE_INTEGER ticks;
        GetSystemTimePreciseAsFileTime(&file_time);
        ticks.LowPart = file_time.dwLowDateTime;
        ticks.HighPart = file_time.dwHighDateTime;
        ticks.QuadPart -= 116444736000000000ull; /* 1601 to 1970, in 100 ns units */
        now->tv_sec = (__time64_t)(ticks.QuadPart / 10000000);
        now->tv_nsec = (long)(ticks.QuadPart % 10000000 * 100);
        return 0;
    }
    errno = EINVAL;
    return -1;
}

int __cdecl nanosleep64(const struct _timespec64 *request, struct _timespec64 *remain)
{
    unsigned long long ms;
    if (request->tv_sec < 0 || request->tv_nsec < 0 || request->tv_nsec >= 1000000000) {
        errno = EINVAL;
        return -1;
    }
    ms = (unsigned long long)request->tv_sec * 1000 + (unsigned long long)request->tv_nsec / 1000000;
    while (ms) {
        DWORD part = ms > 0x7FFFFFFE ? 0x7FFFFFFE : (DWORD)ms;
        Sleep(part);
        ms -= part;
    }
    if (remain) remain->tv_sec = remain->tv_nsec = 0;
    return 0;
}
#endif
