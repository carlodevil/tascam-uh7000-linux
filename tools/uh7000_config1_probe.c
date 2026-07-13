#define _POSIX_C_SOURCE 200809L

/*
 * Opt-in configuration-1 analog playback probe for the TASCAM UH-7000.
 *
 * Configuration 1 is vendor-specific and exposes a stereo isochronous OUT
 * endpoint. This is research tooling, not a packaged driver. It restores
 * configuration 2 before exiting, including after transfer failures.
 */

#include <libusb-1.0/libusb.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <time.h>
#include <unistd.h>

#define VID 0x0644
#define PID 0x8048
#define CONFIG_VENDOR 1
#define CONFIG_UAC2 2
#define STREAM_INTERFACE 1
#define STREAM_ALTSETTING 1
#define STREAM_ENDPOINT 0x02
#define FEEDBACK_ENDPOINT 0x85
#define CAPTURE_INTERFACE 2
#define CAPTURE_ALTSETTING 1
#define CAPTURE_ENDPOINT 0x81
#define SAMPLE_RATE 48000
#define NOMINAL_FRAMES_PER_PACKET 48
#define MAX_FRAMES_PER_PACKET 49
#define CHANNELS 2
#define BYTES_PER_SAMPLE 3
#define PACKET_BYTES (NOMINAL_FRAMES_PER_PACKET * CHANNELS * BYTES_PER_SAMPLE)
#define MAX_PACKET_BYTES (MAX_FRAMES_PER_PACKET * CHANNELS * BYTES_PER_SAMPLE)
#define PACKETS_PER_TRANSFER 6
#define TRANSFER_BYTES (MAX_PACKET_BYTES * PACKETS_PER_TRANSFER)
#define CAPTURE_PACKETS_PER_TRANSFER 6
#define CAPTURE_MAX_FRAMES_PER_PACKET 49
#define CAPTURE_PACKET_BYTES 294
#define CAPTURE_TRANSFER_BYTES (CAPTURE_PACKET_BYTES * CAPTURE_PACKETS_PER_TRANSFER)
#define PACKETS_PER_SECOND 1000
#define CAPTURE_PACKETS_PER_SECOND 1000
#define METRIC_FREQUENCIES 2
#define TWO_PI 6.28318530717958647692
#define CONFIGURATION_LOCK_PATH "/run/tascam-uh7000/configuration.lock"

static const double metric_frequencies[METRIC_FREQUENCIES] = {625.0, 1250.0};

struct stream_context {
    struct libusb_transfer *transfer;
    unsigned long packets_sent;
    unsigned long frames_sent;
    unsigned long packet_limit;
    double phase;
    double phase_step;
    int failed;
    unsigned char *raw_data;
    size_t raw_length;
    size_t raw_offset;
    int stdin_mode;
    unsigned char stdin_buffer[MAX_PACKET_BYTES];
    size_t stdin_length;
    int stdin_eof;
    double feedback_frames_per_packet;
    double frame_remainder;
    int active;
};

struct capture_context {
    struct libusb_transfer *transfer;
    unsigned long packets_received;
    unsigned long packet_limit;
    unsigned long frames_received;
    double sum_squares[CHANNELS];
    double cosine[CHANNELS][METRIC_FREQUENCIES];
    double sine[CHANNELS][METRIC_FREQUENCIES];
    int failed;
    int active;
};

struct feedback_context {
    struct libusb_transfer *transfer;
    unsigned long packets_received;
    uint32_t last_value;
    uint32_t minimum_value;
    uint32_t maximum_value;
    uint64_t value_sum;
    int failed;
    int active;
    struct stream_context *stream;
};

struct kernel_driver_state {
    int detached[4];
};

static volatile sig_atomic_t stop_requested;

static int acquire_configuration_lock(void) {
    const int lock_fd = open(CONFIGURATION_LOCK_PATH, O_RDWR | O_CREAT, 0660);
    if (lock_fd < 0) {
        fprintf(stderr, "could not open configuration lock %s: %s\n",
                CONFIGURATION_LOCK_PATH, strerror(errno));
        return -1;
    }
    if (flock(lock_fd, LOCK_EX | LOCK_NB) != 0) {
        fprintf(stderr, "another UH-7000 configuration-1 stream is active\n");
        close(lock_fd);
        return -1;
    }
    return lock_fd;
}

static void request_stop(int signal_number) {
    (void)signal_number;
    stop_requested = 1;
}

static void fill_stdin_packet(struct stream_context *stream, unsigned char *data, size_t bytes) {
    while (stream->stdin_length < bytes && !stream->stdin_eof) {
        const ssize_t bytes_read = read(STDIN_FILENO,
                                        stream->stdin_buffer + stream->stdin_length,
                                        bytes - stream->stdin_length);
        if (bytes_read > 0) {
            stream->stdin_length += (size_t)bytes_read;
            continue;
        }
        if (bytes_read == 0) {
            stream->stdin_eof = 1;
            break;
        }
        if (errno == EINTR) {
            continue;
        }
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            break;
        }
        perror("read standard input");
        stream->stdin_eof = 1;
        break;
    }
    memcpy(data, stream->stdin_buffer, stream->stdin_length);
    memset(data + stream->stdin_length, 0, bytes - stream->stdin_length);
    stream->stdin_length = 0;
}

static void fill_audio_packet(struct stream_context *stream, unsigned char *data,
                              unsigned int frame_count) {
    const size_t bytes = frame_count * CHANNELS * BYTES_PER_SAMPLE;
    if (stream->stdin_mode) {
        fill_stdin_packet(stream, data, bytes);
        return;
    }
    if (stream->raw_data) {
        for (size_t offset = 0; offset < bytes; offset += BYTES_PER_SAMPLE) {
            memcpy(data + offset, stream->raw_data + stream->raw_offset, BYTES_PER_SAMPLE);
            stream->raw_offset = (stream->raw_offset + BYTES_PER_SAMPLE) % stream->raw_length;
        }
        return;
    }
    for (unsigned int frame = 0; frame < frame_count; ++frame) {
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
    size_t offset = 0;
    for (unsigned int packet = 0; packet < PACKETS_PER_TRANSFER; ++packet) {
        const double requested_frames = stream->feedback_frames_per_packet + stream->frame_remainder;
        unsigned int frame_count = (unsigned int)floor(requested_frames);
        if (frame_count < 1) {
            frame_count = 1;
        } else if (frame_count > MAX_FRAMES_PER_PACKET) {
            frame_count = MAX_FRAMES_PER_PACKET;
        }
        stream->frame_remainder = requested_frames - frame_count;
        const unsigned int bytes = frame_count * CHANNELS * BYTES_PER_SAMPLE;
        fill_audio_packet(stream, stream->transfer->buffer + offset, frame_count);
        stream->transfer->iso_packet_desc[packet].length = bytes;
        stream->frames_sent += frame_count;
        offset += bytes;
    }
    stream->transfer->length = (int)offset;
}

static void LIBUSB_CALL transfer_complete(struct libusb_transfer *transfer) {
    struct stream_context *stream = transfer->user_data;
    if (transfer->status != LIBUSB_TRANSFER_COMPLETED) {
        if (stop_requested && transfer->status == LIBUSB_TRANSFER_CANCELLED) {
            stream->active = 0;
            return;
        }
        fprintf(stderr, "isochronous transfer failed with status %d\n", transfer->status);
        stream->failed = 1;
        stream->active = 0;
        return;
    }
    stream->packets_sent += PACKETS_PER_TRANSFER;
    if ((stream->packet_limit && stream->packets_sent >= stream->packet_limit) ||
        stream->stdin_eof || stop_requested) {
        stream->active = 0;
        return;
    }
    fill_transfer(stream);
    if (libusb_submit_transfer(transfer) != 0) {
        fprintf(stderr, "could not resubmit isochronous transfer\n");
        stream->failed = 1;
        stream->active = 0;
    }
}

static void LIBUSB_CALL capture_complete(struct libusb_transfer *transfer) {
    struct capture_context *capture = transfer->user_data;
    if (transfer->status != LIBUSB_TRANSFER_COMPLETED) {
        if (stop_requested && transfer->status == LIBUSB_TRANSFER_CANCELLED) {
            capture->active = 0;
            return;
        }
        fprintf(stderr, "capture isochronous transfer failed with status %d\n", transfer->status);
        capture->failed = 1;
        capture->active = 0;
        return;
    }
    for (unsigned int packet = 0; packet < CAPTURE_PACKETS_PER_TRANSFER; ++packet) {
        const struct libusb_iso_packet_descriptor *descriptor = &transfer->iso_packet_desc[packet];
        if (descriptor->status != LIBUSB_TRANSFER_COMPLETED ||
            descriptor->actual_length == 0 ||
            descriptor->actual_length > CAPTURE_PACKET_BYTES ||
            descriptor->actual_length % (CHANNELS * BYTES_PER_SAMPLE) != 0) {
            fprintf(stderr, "capture packet %u returned status=%d length=%u\n", packet,
                    descriptor->status, descriptor->actual_length);
            capture->failed = 1;
            capture->active = 0;
            return;
        }
        const unsigned int frame_count =
            descriptor->actual_length / (CHANNELS * BYTES_PER_SAMPLE);
        const unsigned char *data = libusb_get_iso_packet_buffer_simple(transfer, packet);
        for (unsigned int frame = 0; frame < frame_count; ++frame) {
            for (unsigned int channel = 0; channel < CHANNELS; ++channel) {
                const unsigned int offset = (frame * CHANNELS + channel) * BYTES_PER_SAMPLE;
                const double sample = (double)decode_s24le(data + offset) / 8388608.0;
                capture->sum_squares[channel] += sample * sample;
                for (unsigned int metric = 0; metric < METRIC_FREQUENCIES; ++metric) {
                    const double phase = TWO_PI * metric_frequencies[metric] *
                                         (double)capture->frames_received / SAMPLE_RATE;
                    capture->cosine[channel][metric] += sample * cos(phase);
                    capture->sine[channel][metric] += sample * sin(phase);
                }
            }
            ++capture->frames_received;
        }
    }
    capture->packets_received += CAPTURE_PACKETS_PER_TRANSFER;
    if (capture->packet_limit && capture->packets_received >= capture->packet_limit) {
        capture->active = 0;
        return;
    }
    if (libusb_submit_transfer(transfer) != 0) {
        fprintf(stderr, "could not resubmit capture isochronous transfer\n");
        capture->failed = 1;
        capture->active = 0;
    }
}

static void LIBUSB_CALL feedback_complete(struct libusb_transfer *transfer) {
    struct feedback_context *feedback = transfer->user_data;
    if (transfer->status != LIBUSB_TRANSFER_COMPLETED) {
        if (stop_requested && transfer->status == LIBUSB_TRANSFER_CANCELLED) {
            feedback->active = 0;
            return;
        }
        fprintf(stderr, "feedback transfer failed with status %d\n", transfer->status);
        feedback->failed = 1;
        feedback->active = 0;
        return;
    }
    const struct libusb_iso_packet_descriptor *descriptor = &transfer->iso_packet_desc[0];
    if (descriptor->status != LIBUSB_TRANSFER_COMPLETED || descriptor->actual_length != 3) {
        fprintf(stderr, "feedback packet returned status=%d length=%u\n",
                descriptor->status, descriptor->actual_length);
        feedback->failed = 1;
        feedback->active = 0;
        return;
    }
    const unsigned char *data = libusb_get_iso_packet_buffer_simple(transfer, 0);
    feedback->last_value = (uint32_t)data[0] | ((uint32_t)data[1] << 8) |
                           ((uint32_t)data[2] << 16);
    if (feedback->packets_received == 0 || feedback->last_value < feedback->minimum_value) {
        feedback->minimum_value = feedback->last_value;
    }
    if (feedback->last_value > feedback->maximum_value) {
        feedback->maximum_value = feedback->last_value;
    }
    feedback->value_sum += feedback->last_value;
    const double frames_per_packet = (double)feedback->last_value / 16384.0;
    if (frames_per_packet >= 1.0 && frames_per_packet <= MAX_FRAMES_PER_PACKET) {
        feedback->stream->feedback_frames_per_packet = frames_per_packet;
    }
    ++feedback->packets_received;
    if (libusb_submit_transfer(transfer) != 0) {
        fprintf(stderr, "could not resubmit feedback transfer\n");
        feedback->failed = 1;
        feedback->active = 0;
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
    if (length <= 0 || (size_t)length % (CHANNELS * BYTES_PER_SAMPLE) != 0) {
        fprintf(stderr, "raw fixture must be a non-empty multiple of %u bytes\n",
                CHANNELS * BYTES_PER_SAMPLE);
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
                                int remember_for_restore,
                                int stream_only) {
    const int first_interface = stream_only ? STREAM_INTERFACE : 0;
    const int last_interface = stream_only ? STREAM_INTERFACE + 1 : 4;
    for (int interface_number = first_interface; interface_number < last_interface; ++interface_number) {
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
    int output_only = 1;
    int stdin_mode = 0;
    const char *raw_fixture = NULL;
    for (int index = 1; index < argc; ++index) {
        if (strcmp(argv[index], "--execute") == 0) {
            execute = 1;
        } else if (strcmp(argv[index], "--seconds") == 0 && index + 1 < argc) {
            duration_seconds = (unsigned int)strtoul(argv[++index], NULL, 10);
        } else if (strcmp(argv[index], "--raw") == 0 && index + 1 < argc) {
            raw_fixture = argv[++index];
        } else if (strcmp(argv[index], "--output-only") == 0) {
            output_only = 1;
        } else if (strcmp(argv[index], "--duplex-probe") == 0) {
            output_only = 0;
        } else if (strcmp(argv[index], "--stdin") == 0) {
            stdin_mode = 1;
            output_only = 1;
        } else {
            fprintf(stderr,
                    "usage: %s [--seconds N] [--raw S24_3LE_FILE] [--stdin] [--output-only] "
                    "[--duplex-probe] --execute\n",
                    argv[0]);
            return 2;
        }
    }
    if (duration_seconds > 10 || (duration_seconds == 0 && !stdin_mode)) {
        fprintf(stderr, "--seconds must be between 1 and 10, or 0 only with --stdin\n");
        return 2;
    }
    if (raw_fixture && stdin_mode) {
        fprintf(stderr, "--raw and --stdin cannot be used together\n");
        return 2;
    }
    if (!execute) {
        const char *source = stdin_mode ? "stereo S24_3LE stdin" :
                             raw_fixture ? raw_fixture : "stereo 1250 Hz at -30 dBFS";
        printf("dry-run: would stream %s through configuration 1 for %s\n", source,
               duration_seconds ? "the requested duration" : "until interrupted");
        return 0;
    }

    /* Install termination handling before changing USB configuration. */
    signal(SIGINT, request_stop);
    signal(SIGTERM, request_stop);

    libusb_context *usb = NULL;
    libusb_device_handle *handle = NULL;
    struct stream_context stream = {0};
    struct capture_context capture = {0};
    struct feedback_context feedback = {0};
    struct kernel_driver_state kernel_drivers = {0};
    int claimed = 0;
    int capture_claimed = 0;
    int configuration_changed = 0;
    int configuration_lock_fd = -1;
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
    configuration_lock_fd = acquire_configuration_lock();
    if (configuration_lock_fd < 0) {
        result = LIBUSB_ERROR_BUSY;
        goto cleanup;
    }
    int configuration = 0;
    result = libusb_get_configuration(handle, &configuration);
    if (result != 0) {
        fprintf(stderr, "could not read current USB configuration: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    const int preserve_capture = output_only && configuration == CONFIG_VENDOR;
    result = detach_audio_drivers(handle, &kernel_drivers, 1, preserve_capture);
    if (result != 0) {
        goto cleanup;
    }
    if (configuration != CONFIG_VENDOR) {
        result = libusb_set_configuration(handle, CONFIG_VENDOR);
        if (result != 0) {
            fprintf(stderr, "failed to select vendor configuration 1: %s\n", libusb_error_name(result));
            goto cleanup;
        }
    }
    configuration_changed = 1;
    if (stop_requested) {
        goto cleanup;
    }
    result = detach_audio_drivers(handle, &kernel_drivers, 0, preserve_capture);
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
    if (!output_only) {
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
    }
    /* The vendor endpoints can report their previous alternate setting for a
     * few microframes immediately after the switch.  Do not submit audio until
     * both selected interfaces have settled. */
    const struct timespec endpoint_settle = {.tv_sec = 0, .tv_nsec = 100000000L};
    nanosleep(&endpoint_settle, NULL);
    if (raw_fixture && load_raw_fixture(raw_fixture, &stream) != 0) {
        result = LIBUSB_ERROR_OTHER;
        goto cleanup;
    }
    stream.stdin_mode = stdin_mode;
    if (stdin_mode) {
        const int flags = fcntl(STDIN_FILENO, F_GETFL);
        if (flags < 0 || fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK) < 0) {
            perror("configure standard input");
            result = LIBUSB_ERROR_OTHER;
            goto cleanup;
        }
    }

    stream.transfer = libusb_alloc_transfer(PACKETS_PER_TRANSFER);
    if (!stream.transfer) {
        fprintf(stderr, "failed to allocate isochronous transfer\n");
        goto cleanup;
    }
    feedback.transfer = libusb_alloc_transfer(1);
    if (!feedback.transfer) {
        fprintf(stderr, "failed to allocate feedback transfer\n");
        goto cleanup;
    }
    if (!output_only) {
        capture.transfer = libusb_alloc_transfer(CAPTURE_PACKETS_PER_TRANSFER);
        if (!capture.transfer) {
            fprintf(stderr, "failed to allocate capture isochronous transfer\n");
            goto cleanup;
        }
    }
    unsigned char *buffer = calloc(1, TRANSFER_BYTES);
    if (!buffer) {
        fprintf(stderr, "failed to allocate isochronous buffer\n");
        goto cleanup;
    }
    stream.packet_limit = duration_seconds ? duration_seconds * PACKETS_PER_SECOND : 0;
    stream.feedback_frames_per_packet = NOMINAL_FRAMES_PER_PACKET;
    capture.packet_limit = (output_only || duration_seconds == 0) ? 0 :
        duration_seconds * CAPTURE_PACKETS_PER_SECOND + CAPTURE_PACKETS_PER_TRANSFER;
    stream.phase_step = TWO_PI * 1250.0 / SAMPLE_RATE;
    libusb_fill_iso_transfer(stream.transfer, handle, STREAM_ENDPOINT, buffer, TRANSFER_BYTES,
                             PACKETS_PER_TRANSFER,
                             transfer_complete, &stream, 1000);
    stream.transfer->flags = LIBUSB_TRANSFER_FREE_BUFFER;
    libusb_set_iso_packet_lengths(stream.transfer, PACKET_BYTES);
    unsigned char *feedback_buffer = calloc(1, 3);
    if (!feedback_buffer) {
        fprintf(stderr, "failed to allocate feedback buffer\n");
        result = LIBUSB_ERROR_NO_MEM;
        goto cleanup;
    }
    libusb_fill_iso_transfer(feedback.transfer, handle, FEEDBACK_ENDPOINT, feedback_buffer, 3, 1,
                             feedback_complete, &feedback, 1000);
    feedback.transfer->flags = LIBUSB_TRANSFER_FREE_BUFFER;
    libusb_set_iso_packet_lengths(feedback.transfer, 3);
    feedback.stream = &stream;
    result = libusb_submit_transfer(feedback.transfer);
    if (result != 0) {
        fprintf(stderr, "failed to submit feedback transfer: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    feedback.active = 1;
    if (!output_only) {
        unsigned char *capture_buffer = calloc(1, CAPTURE_TRANSFER_BYTES);
        if (!capture_buffer) {
            fprintf(stderr, "failed to allocate capture isochronous buffer\n");
            result = LIBUSB_ERROR_NO_MEM;
            goto cleanup;
        }
        libusb_fill_iso_transfer(capture.transfer, handle, CAPTURE_ENDPOINT, capture_buffer,
                                 CAPTURE_TRANSFER_BYTES,
                                 CAPTURE_PACKETS_PER_TRANSFER, capture_complete, &capture, 1000);
        capture.transfer->flags = LIBUSB_TRANSFER_FREE_BUFFER;
        libusb_set_iso_packet_lengths(capture.transfer, CAPTURE_PACKET_BYTES);
        result = libusb_submit_transfer(capture.transfer);
        if (result != 0) {
            fprintf(stderr, "failed to submit capture isochronous transfer: %s\n",
                    libusb_error_name(result));
            goto cleanup;
        }
        capture.active = 1;
    }
    fill_transfer(&stream);
    result = libusb_submit_transfer(stream.transfer);
    if (result != 0) {
        fprintf(stderr, "failed to submit isochronous transfer: %s\n", libusb_error_name(result));
        goto cleanup;
    }
    stream.active = 1;
    /* A duplex probe is bounded by the output stream. Continuing capture after
     * a finite output stream ends can leave the vendor capture endpoint active
     * indefinitely when it stops producing packets. */
    while (!stop_requested && !stream.failed && !capture.failed && stream.active &&
           (stream.packet_limit == 0 || stream.packets_sent < stream.packet_limit)) {
        struct timeval timeout = {.tv_sec = 1, .tv_usec = 0};
        result = libusb_handle_events_timeout_completed(usb, &timeout, NULL);
        if (result == LIBUSB_ERROR_INTERRUPTED) {
            result = 0;
        } else if (result != 0) {
            fprintf(stderr, "libusb event loop failed: %s\n", libusb_error_name(result));
            stream.failed = 1;
        }
    }
    if (!output_only && capture.frames_received == 0) {
        fprintf(stderr, "capture endpoint returned no audio frames\n");
        capture.failed = 1;
    }
    printf("configuration-1 stream completed: packets=%lu frames=%lu frames_per_ms=%.6f status=%s\n",
           stream.packets_sent, stream.frames_sent,
           stream.packets_sent ? (double)stream.frames_sent / stream.packets_sent : 0.0,
           (stream.failed || capture.failed) ? "failed" : "ok");
    if (feedback.packets_received) {
        printf("feedback: packets=%lu raw=0x%06x frames_per_ms=%.6f avg=%.6f range=%.6f..%.6f\n",
               feedback.packets_received, feedback.last_value,
               (double)feedback.last_value / 16384.0,
               (double)feedback.value_sum / feedback.packets_received / 16384.0,
               (double)feedback.minimum_value / 16384.0,
               (double)feedback.maximum_value / 16384.0);
    }
    if (!output_only && capture.frames_received) {
        for (unsigned int channel = 0; channel < CHANNELS; ++channel) {
            const double rms = sqrt(capture.sum_squares[channel] / capture.frames_received);
            printf("capture ch%u: rms=%.2f dBFS", channel + 1, dbfs(rms));
            for (unsigned int metric = 0; metric < METRIC_FREQUENCIES; ++metric) {
                const double tone = 2.0 * hypot(capture.cosine[channel][metric],
                                                capture.sine[channel][metric]) /
                                    capture.frames_received;
                printf(" %.0fHz=%.2f dBFS", metric_frequencies[metric], dbfs(tone));
            }
            printf("\n");
        }
    }

cleanup:
    stop_requested = 1;
    if (stream.transfer && stream.active) {
        libusb_cancel_transfer(stream.transfer);
    }
    if (capture.transfer && capture.active) {
        libusb_cancel_transfer(capture.transfer);
    }
    if (feedback.transfer && feedback.active) {
        libusb_cancel_transfer(feedback.transfer);
    }
    while ((stream.transfer && stream.active) || (capture.transfer && capture.active) ||
           (feedback.transfer && feedback.active)) {
        struct timeval timeout = {.tv_sec = 1, .tv_usec = 0};
        const int event_result = libusb_handle_events_timeout_completed(usb, &timeout, NULL);
        if (event_result != 0 && event_result != LIBUSB_ERROR_INTERRUPTED) {
            fprintf(stderr, "could not drain cancelled transfers: %s\n", libusb_error_name(event_result));
            break;
        }
    }
    free(stream.raw_data);
    if (capture.transfer) {
        libusb_free_transfer(capture.transfer);
    }
    if (feedback.transfer) {
        libusb_free_transfer(feedback.transfer);
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
        /* Every audio interface must be detached before configuration 2 can
         * be selected, including a capture interface retained for a config-1
         * output-only diagnostic. */
        const int detach_result = detach_audio_drivers(handle, &kernel_drivers, 0, 0);
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
    if (configuration_lock_fd >= 0) {
        close(configuration_lock_fd);
    }
    libusb_close(handle);
    libusb_exit(usb);
    return (result != 0 || stream.failed || capture.failed || restore_failed) ? 1 : 0;
}
