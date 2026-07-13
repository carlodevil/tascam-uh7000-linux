/*
 * Opt-in configuration-1 analog playback probe for the TASCAM UH-7000.
 *
 * Configuration 1 is vendor-specific and exposes a stereo isochronous OUT
 * endpoint. This is research tooling, not a packaged driver. It restores
 * configuration 2 before exiting, including after transfer failures.
 */

#include <libusb-1.0/libusb.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define VID 0x0644
#define PID 0x8048
#define CONFIG_VENDOR 1
#define CONFIG_UAC2 2
#define STREAM_INTERFACE 1
#define STREAM_ALTSETTING 1
#define STREAM_ENDPOINT 0x02
#define SAMPLE_RATE 48000
#define FRAMES_PER_PACKET 48
#define CHANNELS 2
#define BYTES_PER_SAMPLE 3
#define PACKET_BYTES (FRAMES_PER_PACKET * CHANNELS * BYTES_PER_SAMPLE)
#define TWO_PI 6.28318530717958647692

struct stream_context {
    struct libusb_transfer *transfer;
    unsigned long packets_sent;
    unsigned long packet_limit;
    double phase;
    double phase_step;
    int failed;
};

static void fill_packet(struct stream_context *stream) {
    unsigned char *data = stream->transfer->buffer;
    for (unsigned int frame = 0; frame < FRAMES_PER_PACKET; ++frame) {
        const int32_t sample = (int32_t)(0.0316227766 * 8388607.0 * sin(stream->phase));
        stream->phase += stream->phase_step;
        if (stream->phase >= TWO_PI) {
            stream->phase -= TWO_PI;
        }
        for (unsigned int channel = 0; channel < CHANNELS; ++channel) {
            const unsigned int offset = (frame * CHANNELS + channel) * BYTES_PER_SAMPLE;
            data[offset] = (unsigned char)(sample & 0xff);
            data[offset + 1] = (unsigned char)((sample >> 8) & 0xff);
            data[offset + 2] = (unsigned char)((sample >> 16) & 0xff);
        }
    }
}

static void LIBUSB_CALL transfer_complete(struct libusb_transfer *transfer) {
    struct stream_context *stream = transfer->user_data;
    if (transfer->status != LIBUSB_TRANSFER_COMPLETED) {
        fprintf(stderr, "isochronous transfer failed: %s\n", libusb_error_name(transfer->status));
        stream->failed = 1;
        return;
    }
    ++stream->packets_sent;
    if (stream->packets_sent >= stream->packet_limit) {
        return;
    }
    fill_packet(stream);
    if (libusb_submit_transfer(transfer) != 0) {
        fprintf(stderr, "could not resubmit isochronous transfer\n");
        stream->failed = 1;
    }
}

static int restore_uac2(libusb_device_handle *handle) {
    const int result = libusb_set_configuration(handle, CONFIG_UAC2);
    if (result != 0) {
        fprintf(stderr, "failed to restore UAC2 configuration 2: %s\n", libusb_error_name(result));
        return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    unsigned int duration_seconds = 2;
    int execute = 0;
    for (int index = 1; index < argc; ++index) {
        if (strcmp(argv[index], "--execute") == 0) {
            execute = 1;
        } else if (strcmp(argv[index], "--seconds") == 0 && index + 1 < argc) {
            duration_seconds = (unsigned int)strtoul(argv[++index], NULL, 10);
        } else {
            fprintf(stderr, "usage: %s [--seconds N] --execute\n", argv[0]);
            return 2;
        }
    }
    if (duration_seconds == 0 || duration_seconds > 10) {
        fprintf(stderr, "--seconds must be between 1 and 10\n");
        return 2;
    }
    if (!execute) {
        printf("dry-run: would stream stereo 1250 Hz at -30 dBFS through configuration 1 for %u seconds\n",
               duration_seconds);
        return 0;
    }

    libusb_context *usb = NULL;
    libusb_device_handle *handle = NULL;
    struct stream_context stream = {0};
    int claimed = 0;
    int result = libusb_init(&usb);
    if (result != 0) {
        fprintf(stderr, "libusb initialization failed: %s\n", libusb_error_name(result));
        return 1;
    }
    handle = libusb_open_device_with_vid_pid(usb, VID, PID);
    if (!handle) {
        fprintf(stderr, "UH-7000 %04x:%04x not found\n", VID, PID);
        libusb_exit(usb);
        return 1;
    }
    result = libusb_set_configuration(handle, CONFIG_VENDOR);
    if (result != 0) {
        fprintf(stderr, "failed to select vendor configuration 1: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    result = libusb_claim_interface(handle, STREAM_INTERFACE);
    if (result != 0) {
        fprintf(stderr, "failed to claim vendor stream interface: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    claimed = 1;
    result = libusb_set_interface_alt_setting(handle, STREAM_INTERFACE, STREAM_ALTSETTING);
    if (result != 0) {
        fprintf(stderr, "failed to select vendor stream altsetting: %s\n", libusb_error_name(result));
        goto cleanup;
    }

    stream.transfer = libusb_alloc_transfer(1);
    if (!stream.transfer) {
        fprintf(stderr, "failed to allocate isochronous transfer\n");
        goto cleanup;
    }
    unsigned char *buffer = calloc(1, PACKET_BYTES);
    if (!buffer) {
        fprintf(stderr, "failed to allocate isochronous buffer\n");
        goto cleanup;
    }
    stream.packet_limit = duration_seconds * 1000UL;
    stream.phase_step = TWO_PI * 1250.0 / SAMPLE_RATE;
    libusb_fill_iso_transfer(stream.transfer, handle, STREAM_ENDPOINT, buffer, PACKET_BYTES, 1,
                             transfer_complete, &stream, 1000);
    stream.transfer->flags = LIBUSB_TRANSFER_FREE_BUFFER;
    libusb_set_iso_packet_lengths(stream.transfer, PACKET_BYTES);
    fill_packet(&stream);
    result = libusb_submit_transfer(stream.transfer);
    if (result != 0) {
        fprintf(stderr, "failed to submit isochronous transfer: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    while (!stream.failed && stream.packets_sent < stream.packet_limit) {
        struct timeval timeout = {.tv_sec = 1, .tv_usec = 0};
        result = libusb_handle_events_timeout_completed(usb, &timeout, NULL);
        if (result != 0 && result != LIBUSB_ERROR_INTERRUPTED) {
            fprintf(stderr, "libusb event loop failed: %s\n", libusb_error_name(result));
            stream.failed = 1;
        }
    }
    printf("configuration-1 stream completed: packets=%lu status=%s\n", stream.packets_sent,
           stream.failed ? "failed" : "ok");

cleanup:
    if (stream.transfer) {
        libusb_free_transfer(stream.transfer);
    }
    if (claimed) {
        libusb_release_interface(handle, STREAM_INTERFACE);
    }
    const int restore_failed = restore_uac2(handle);
    libusb_close(handle);
    libusb_exit(usb);
    return (result != 0 || stream.failed || restore_failed) ? 1 : 0;
}
