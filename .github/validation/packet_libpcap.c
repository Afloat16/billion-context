#include <pcap/pcap.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static int write_capture(const char *frames, const char *output) {
    FILE *input = fopen(frames, "rb");
    if (!input) {
        perror("frame input");
        return 2;
    }
    pcap_t *pcap = pcap_open_dead(DLT_EN10MB, 65535);
    if (!pcap) {
        fclose(input);
        return 2;
    }
    pcap_dumper_t *dump = pcap_dump_open(pcap, output);
    if (!dump) {
        fprintf(stderr, "%s\n", pcap_geterr(pcap));
        pcap_close(pcap);
        fclose(input);
        return 2;
    }
    uint64_t count = 0;
    int status = 0;
    unsigned char packet[65535];
    for (;;) {
        unsigned char length[4];
        size_t got = fread(length, 1, sizeof(length), input);
        if (got == 0 && feof(input)) {
            break;
        }
        if (got != sizeof(length)) {
            status = 2;
            break;
        }
        uint32_t size = (uint32_t)length[0] | ((uint32_t)length[1] << 8)
            | ((uint32_t)length[2] << 16) | ((uint32_t)length[3] << 24);
        if (size > sizeof(packet) || fread(packet, 1, size, input) != size) {
            status = 2;
            break;
        }
        struct pcap_pkthdr header;
        memset(&header, 0, sizeof(header));
        header.ts.tv_sec = (time_t)(1700000000ULL + count);
        header.ts.tv_usec = 500;
        header.caplen = size;
        header.len = size;
        pcap_dump((u_char *)dump, &header, packet);
        count++;
    }
    if (pcap_dump_flush(dump) != 0) {
        fprintf(stderr, "%s\n", pcap_geterr(pcap));
        status = 2;
    }
    pcap_dump_close(dump);
    pcap_close(pcap);
    fclose(input);
    fprintf(stderr, "native writer: %" PRIu64 " packets\n", count);
    return status;
}

static int read_capture(const char *path) {
    char error[PCAP_ERRBUF_SIZE] = {0};
    pcap_t *pcap = pcap_open_offline(path, error);
    if (!pcap) {
        fprintf(stderr, "%s\n", error);
        return 2;
    }
    uint64_t count = 0;
    int result;
    struct pcap_pkthdr *header;
    const u_char *packet;
    while ((result = pcap_next_ex(pcap, &header, &packet)) == 1) {
        count++;
        printf("%" PRIu64 "\t%" PRIu32 "\t%" PRIu32 "\t%" PRIdMAX "\t%" PRIdMAX "\t%d\t",
               count, header->caplen, header->len, (intmax_t)header->ts.tv_sec,
               (intmax_t)header->ts.tv_usec, pcap_datalink(pcap));
        for (uint32_t i = 0; i < header->caplen; i++) {
            printf("%02x", packet[i]);
        }
        putchar('\n');
    }
    if (result != -2) {
        fprintf(stderr, "%s\n", pcap_geterr(pcap));
    }
    pcap_close(pcap);
    return result == -2 ? 0 : 2;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts(pcap_lib_version());
        return 0;
    }
    if (argc == 4 && strcmp(argv[1], "write") == 0) {
        return write_capture(argv[2], argv[3]);
    }
    if (argc == 3 && strcmp(argv[1], "read") == 0) {
        return read_capture(argv[2]);
    }
    fputs("expected write <frames> <capture> or read <capture>\n", stderr);
    return 2;
}
