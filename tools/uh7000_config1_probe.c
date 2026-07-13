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
#define CAPTURE_INTERFACE 2
#define CAPTURE_ALTSETTING 1
#define CAPTURE_ENDPOINT 0x81
#define SAMPLE_RATE 48000
#define FRAMES_PER_PACKET 48
#define CHANNELS 2
#define BYTES_PER_SAMPLE 3
#define PACKET_BYTES (FRAMES_PER_PACKET * CHANNELS * BYTES_PER_SAMPLE)
#define PACKETS_PER_TRANSFER 6
#define TRANSFER_BYTES (PACKET_BYTES * PACKETS_PER_TRANSFER)
#define TWO_PI 6.28318530717958647692

struct stream_context {
    struct libusb_transfer *transfer;
    unsigned long packets_sent;
    unsigned long packet_limit;
    double phase;
    double phase_step;
    int failed;
    unsigned char *raw_data;
    size_t raw_length;
    size_t raw_offset;
};

struct capture_context {
    struct libusb_transfer *transfer;
    unsigned long packets_received;
    unsigned long packet_limit;
    unsigned long frames_received;
    double sum_squares[CHANNELS];
    double cosine[CHANNELS];
    double sine[CHANNELS];
    int failed;
};

struct kernel_driver_state {
    int detached[4];
};

static void fill_audio_packet(struct stream_context *stream, unsigned char *data) {
    if (stream->raw_data) {
        memcpy(data, stream->raw_data + stream->raw_offset, PACKET_BYTES);
        stream->raw_offset = (stream->raw_offset + PACKET_BYTES) % stream->raw_length;
        return;
    }
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

static int32_t decode_s24le(const unsigned char *data) {
    int32_t sample = (int32_t)data[0] | ((int32_t)data[1] << 8) | ((int32_t)data[2] << 16);
    return (sample & 0x800000) ? sample | ~0xffffff : sample;
}

static double dbfs(double amplitude) {
    return 20.0 * log10(amplitude > 1e-12 ? amplitude : 1e-12);
}

static void fill_transfer(struct stream_context *stream) {
    for (unsigned int packet = 0; packet < PACKETS_PER_TRANSFER; ++packet) {
        fill_audio_packet(stream, stream->transfer->buffer + packet * PACKET_BYTES);
    }
}

static void LIBUSB_CALL transfer_complete(struct libusb_transfer *transfer) {
    struct stream_context *stream = transfer->user_data;
    if (transfer->status != LIBUSB_TRANSFER_COMPLETED) {
        fprintf(stderr, "isochronous transfer failed with status %d\n", transfer->status);
        stream->failed = 1;
        return;
    }
    stream->packets_sent += PACKETS_PER_TRANSFER;
    if (stream->packets_sent >= stream->packet_limit) {
        return;
    }
    fill_transfer(stream);
    if (libusb_submit_transfer(transfer) != 0) {
        fprintf(stderr, "could not resubmit isochronous transfer\n");
        stream->failed = 1;
    }
}

static void LIBUSB_CALL capture_complete(struct libusb_transfer *transfer) {
    struct capture_context *capture = transfer->user_data;
    if (transfer->status != LIBUSB_TRANSFER_COMPLETED) {
        fprintf(stderr, "capture isochronous transfer failed with status %d\n", transfer->status);
        capture->failed = 1;
        return;
    }
    for (unsigned int packet = 0; packet < PACKETS_PER_TRANSFER; ++packet) {
        const struct libusb_iso_packet_descriptor *descriptor = &transfer->iso_packet_desc[packet];
        if (descriptor->status != LIBUSB_TRANSFER_COMPLETED || descriptor->actual_length != PACKET_BYTES) {
            fprintf(stderr, "capture packet %u returned status=%d length=%u\n", packet,
                    descriptor->status, descriptor->actual_length);
            capture->failed = 1;
            return;
        }
        const unsigned char *data = libusb_get_iso_packet_buffer_simple(transfer, packet);
        for (unsigned int frame = 0; frame < FRAMES_PER_PACKET; ++frame) {
            const double phase = TWO_PI * 1250.0 * (double)capture->frames_received / SAMPLE_RATE;
            for (unsigned int channel = 0; channel < CHANNELS; ++channel) {
                const unsigned int offset = (frame * CHANNELS + channel) * BYTES_PER_SAMPLE;
                const double sample = (double)decode_s24le(data + offset) / 8388608.0;
                capture->sum_squares[channel] += sample * sample;
                capture->cosine[channel] += sample * cos(phase);
                capture->sine[channel] += sample * sin(phase);
            }
            ++capture->frames_received;
        }
    }
    capture->packets_received += PACKETS_PER_TRANSFER;
    if (capture->packets_received >= capture->packet_limit) {
        return;
    }
    if (libusb_submit_transfer(transfer) != 0) {
        fprintf(stderr, "could not resubmit capture isochronous transfer\n");
        capture->failed = 1;
    }
}

static int load_raw_fixture(const char *path, struct stream_context *stream) {
    FILE *file = fopen(path, "rb");
    if (!file) {
        perror(path);
        return 1;
    }
    if (fseek(file, 0, SEEK_END) != 0) {
        perror("could not seek raw fixture");
        fclose(file);
        return 1;
    }
    const long length = ftell(file);
    if (length <= 0 || (size_t)length % PACKET_BYTES != 0) {
        fprintf(stderr, "raw fixture must be a non-empty multiple of %u bytes\n", PACKET_BYTES);
        fclose(file);
        return 1;
    }
    rewind(file);
    stream->raw_data = malloc((size_t)length);
    if (!stream->raw_data || fread(stream->raw_data, 1, (size_t)length, file) != (size_t)length) {
        fprintf(stderr, "could not read raw fixture\n");
        free(stream->raw_data);
        stream->raw_data = NULL;
        fclose(file);
        return 1;
    }
    fclose(file);
    stream->raw_length = (size_t)length;
    return 0;
}

static int restore_uac2(libusb_device_handle *handle) {
    const int result = libusb_set_configuration(handle, CONFIG_UAC2);
    if (result != 0) {
        fprintf(stderr, "failed to restore UAC2 configuration 2: %s\n", libusb_error_name(result));
        return 1;
    }
    return 0;
}

static int detach_audio_drivers(libusb_device_handle *handle,
                                struct kernel_driver_state *state,
                                int remember_for_restore) {
    for (int interface_number = 0; interface_number < 4; ++interface_number) {
        const int active = libusb_kernel_driver_active(handle, interface_number);
        if (active == LIBUSB_ERROR_NOT_FOUND) {
            continue;
        }
        if (active < 0) {
            fprintf(stderr, "could not inspect kernel driver for interface %d: %s\n",
                    interface_number, libusb_error_name(active));
            return active;
        }
        if (active == 1) {
            const int result = libusb_detach_kernel_driver(handle, interface_number);
            if (result != 0) {
                fprintf(stderr, "could not detach kernel driver for interface %d: %s\n",
                        interface_number, libusb_error_name(result));
                return result;
            }
            if (remember_for_restore) {
                state->detached[interface_number] = 1;
            }
        }
    }
    return 0;
}

static int reattach_audio_drivers(libusb_device_handle *handle,
                                  const struct kernel_driver_state *state) {
    int failed = 0;
    for (int interface_number = 0; interface_number < 4; ++interface_number) {
        if (!state->detached[interface_number]) {
            continue;
        }
        const int result = libusb_attach_kernel_driver(handle, interface_number);
        if (result != 0 && result != LIBUSB_ERROR_BUSY && result != LIBUSB_ERROR_NOT_FOUND) {
            fprintf(stderr, "could not reattach kernel driver for interface %d: %s\n",
                    interface_number, libusb_error_name(result));
            failed = 1;
        }
    }
    return failed;
}

int main(int argc, char **argv) {
    unsigned int duration_seconds = 2;
    int execute = 0;
    const char *raw_fixture = NULL;
    for (int index = 1; index < argc; ++index) {
        if (strcmp(argv[index], "--execute") == 0) {
            execute = 1;
        } else if (strcmp(argv[index], "--seconds") == 0 && index + 1 < argc) {
            duration_seconds = (unsigned int)strtoul(argv[++index], NULL, 10);
        } else if (strcmp(argv[index], "--raw") == 0 && index + 1 < argc) {
            raw_fixture = argv[++index];
        } else {
            fprintf(stderr, "usage: %s [--seconds N] [--raw S24_3LE_FILE] --execute\n", argv[0]);
            return 2;
        }
    }
    if (duration_seconds == 0 || duration_seconds > 10) {
        fprintf(stderr, "--seconds must be between 1 and 10\n");
        return 2;
    }
    if (!execute) {
        printf("dry-run: would stream %s through configuration 1 for %u seconds\n",
               raw_fixture ? raw_fixture : "stereo 1250 Hz at -30 dBFS", duration_seconds);
        return 0;
    }

    libusb_context *usb = NULL;
    libusb_device_handle *handle = NULL;
    struct stream_context stream = {0};
    struct capture_context capture = {0};
    struct kernel_driver_state kernel_drivers = {0};
    int claimed = 0;
    int capture_claimed = 0;
    int configuration_changed = 0;
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
    result = detach_audio_drivers(handle, &kernel_drivers, 1);
    if (result != 0) {
        goto cleanup;
    }
    result = libusb_set_configuration(handle, CONFIG_VENDOR);
    if (result != 0) {
        fprintf(stderr, "failed to select vendor configuration 1: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    configuration_changed = 1;
    result = detach_audio_drivers(handle, &kernel_drivers, 0);
    if (result != 0) {
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
    result = libusb_claim_interface(handle, CAPTURE_INTERFACE);
    if (result != 0) {
        fprintf(stderr, "failed to claim vendor capture interface: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    capture_claimed = 1;
    result = libusb_set_interface_alt_setting(handle, CAPTURE_INTERFACE, CAPTURE_ALTSETTING);
    if (result != 0) {
        fprintf(stderr, "failed to select vendor capture altsetting: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    if (raw_fixture && load_raw_fixture(raw_fixture, &stream) != 0) {
        result = LIBUSB_ERROR_OTHER;
        goto cleanup;
    }

    stream.transfer = libusb_alloc_transfer(PACKETS_PER_TRANSFER);
    if (!stream.transfer) {
        fprintf(stderr, "failed to allocate isochronous transfer\n");
        goto cleanup;
    }
    capture.transfer = libusb_alloc_transfer(PACKETS_PER_TRANSFER);
    if (!capture.transfer) {
        fprintf(stderr, "failed to allocate capture isochronous transfer\n");
        goto cleanup;
    }
    unsigned char *buffer = calloc(1, TRANSFER_BYTES);
    if (!buffer) {
        fprintf(stderr, "failed to allocate isochronous buffer\n");
        goto cleanup;
    }
    stream.packet_limit = duration_seconds * 1000UL;
    capture.packet_limit = stream.packet_limit + PACKETS_PER_TRANSFER;
    stream.phase_step = TWO_PI * 1250.0 / SAMPLE_RATE;
    libusb_fill_iso_transfer(stream.transfer, handle, STREAM_ENDPOINT, buffer, TRANSFER_BYTES,
                             PACKETS_PER_TRANSFER,
                             transfer_complete, &stream, 1000);
    stream.transfer->flags = LIBUSB_TRANSFER_FREE_BUFFER;
    libusb_set_iso_packet_lengths(stream.transfer, PACKET_BYTES);
    unsigned char *capture_buffer = calloc(1, TRANSFER_BYTES);
    if (!capture_buffer) {
        fprintf(stderr, "failed to allocate capture isochronous buffer\n");
        result = LIBUSB_ERROR_NO_MEM;
        goto cleanup;
    }
    libusb_fill_iso_transfer(capture.transfer, handle, CAPTURE_ENDPOINT, capture_buffer, TRANSFER_BYTES,
                             PACKETS_PER_TRANSFER, capture_complete, &capture, 1000);
    capture.transfer->flags = LIBUSB_TRANSFER_FREE_BUFFER;
    libusb_set_iso_packet_lengths(capture.transfer, PACKET_BYTES);
    result = libusb_submit_transfer(capture.transfer);
    if (result != 0) {
        fprintf(stderr, "failed to submit capture isochronous transfer: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    fill_transfer(&stream);
    result = libusb_submit_transfer(stream.transfer);
    if (result != 0) {
        fprintf(stderr, "failed to submit isochronous transfer: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    while (!stream.failed && !capture.failed &&
           (stream.packets_sent < stream.packet_limit || capture.packets_received < capture.packet_limit)) {
        struct timeval timeout = {.tv_sec = 1, .tv_usec = 0};
        result = libusb_handle_events_timeout_completed(usb, &timeout, NULL);
        if (result != 0 && result != LIBUSB_ERROR_INTERRUPTED) {
            fprintf(stderr, "libusb event loop failed: %s\n", libusb_error_name(result));
            stream.failed = 1;
        }
    }
    printf("configuration-1 stream completed: packets=%lu status=%s\n", stream.packets_sent,
           (stream.failed || capture.failed) ? "failed" : "ok");
    if (capture.frames_received) {
        for (unsigned int channel = 0; channel < CHANNELS; ++channel) {
            const double rms = sqrt(capture.sum_squares[channel] / capture.frames_received);
            const double tone = 2.0 * hypot(capture.cosine[channel], capture.sine[channel]) /
                                capture.frames_received;
            printf("capture ch%u: rms=%.2f dBFS 1250Hz=%.2f dBFS\n", channel + 1,
                   dbfs(rms), dbfs(tone));
        }
    }

cleanup:
    free(stream.raw_data);
    if (capture.transfer) {
        libusb_free_transfer(capture.transfer);
    }
    if (stream.transfer) {
        libusb_free_transfer(stream.transfer);
    }
    if (claimed) {
        libusb_release_interface(handle, STREAM_INTERFACE);
    }
    if (capture_claimed) {
        libusb_release_interface(handle, CAPTURE_INTERFACE);
    }
    int restore_failed = 0;
    if (configuration_changed) {
        const int detach_result = detach_audio_drivers(handle, &kernel_drivers, 0);
        if (detach_result != 0) {
            restore_failed = 1;
        }
    }
    if (configuration_changed && restore_failed == 0) {
        restore_failed = restore_uac2(handle);
    }
    if (restore_failed == 0) {
        restore_failed = reattach_audio_drivers(handle, &kernel_drivers);
    }
    libusb_close(handle);
    libusb_exit(usb);
    return (result != 0 || stream.failed || capture.failed || restore_failed) ? 1 : 0;
}
