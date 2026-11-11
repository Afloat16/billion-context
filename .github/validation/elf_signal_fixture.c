#define _GNU_SOURCE
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc != 2) return 90;
    if (strcmp(argv[1], "kill-segv") == 0) {
        return kill(getpid(), SIGSEGV);
    }
    if (strcmp(argv[1], "raise-ill") == 0) {
        return raise(SIGILL);
    }
    if (strcmp(argv[1], "queue-bus") == 0) {
        const union sigval value = {.sival_int = 0x13579};
        return sigqueue(getpid(), SIGBUS, value);
    }
    if (strcmp(argv[1], "timer-segv") == 0) {
        timer_t timer;
        struct sigevent event = {.sigev_notify = SIGEV_SIGNAL, .sigev_signo = SIGSEGV};
        const struct itimerspec delay = {.it_value = {.tv_nsec = 1000000}};
        if (timer_create(CLOCK_MONOTONIC, &event, &timer) != 0) return 91;
        if (timer_settime(timer, 0, &delay, NULL) != 0) return 92;
        for (;;) pause();
    }
    if (strcmp(argv[1], "kill-abrt") == 0) {
        return kill(getpid(), SIGABRT);
    }
    if (strcmp(argv[1], "fault-segv") == 0) {
        void *page = mmap(NULL, 4096, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (page == MAP_FAILED) return 93;
        *(volatile char *)page = 1;
        return 94;
    }
    if (strcmp(argv[1], "illegal-ill") == 0) {
        __asm__ volatile("ud2");
        return 95;
    }
    if (strcmp(argv[1], "divide-fpe") == 0) {
        __asm__ volatile("xorl %%edx, %%edx\nmovl $1, %%eax\nxorl %%ecx, %%ecx\nidivl %%ecx" : : : "eax", "ecx", "edx", "cc");
        return 96;
    }
    if (strcmp(argv[1], "kernel-trap") == 0) {
        __asm__ volatile("int3");
        return 97;
    }
    return 98;
}
