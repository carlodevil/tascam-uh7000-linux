# UH-7000 Windows panel visual reference

Clean-room reference capture of the official Windows **TASCAM UH-7000 Mixer
Panel** for implementation and visual comparison of `uh7000-panel`.

## Capture environment

- Panel/driver version: **1.02**
- Device firmware: **1.08**
- Connection: **USB 2.0**
- Sample width/rate: **24-bit / 48 kHz**
- Digital input: **no valid signal**
- Native window client area: **1026 x 717 px**
- Date: **2026-07-13**
- Initial and restored mode: **Multitrack**
- Initial and restored line-output route: **Computer 1 and 2**
- Digital-output route: **Master L and R**
- Digital-output format: **S/PDIF**

These images are research fixtures only. Do not copy TASCAM artwork into the
installed Linux package; reproduce the layout and behavior with original
assets.

## Primary views

| File | State represented |
| --- | --- |
| `interface-main.jpg` | Interface tab in Multitrack mode |
| `mixer-main.jpg` | Mixer tab in the starting Multitrack state |
| `interface-stereo-mix.jpg` | Interface tab after selecting Stereo Mix |
| `mixer-stereo-mix.jpg` | Mixer tab in Stereo Mix mode |
| `mixer-main-restored.jpg` | Final verification after restoring Multitrack and the original line-output route |
| `effects-compressor.jpg` | Compressor and shared Reverb panel |
| `effects-noise-suppressor.jpg` | Noise Suppressor and shared Reverb panel |
| `effects-de-esser.jpg` | De-esser and shared Reverb panel |
| `effects-exciter.jpg` | Exciter and shared Reverb panel |
| `effects-eq.jpg` | Three-band EQ and shared Reverb panel |
| `effects-limiter-low-cut.jpg` | Limiter/Low-cut and shared Reverb panel |

## Interface option lists

Transient controls can be returned as multiple images. `z0` is the complete
panel capture; higher z-order files are tightly cropped popup layers from the
same instant.

| Prefix | Visible choices |
| --- | --- |
| `interface-mixer-mode-options-*` | Multitrack; Stereo Mix |
| `interface-audio-performance-options-*` | highest latency; high latency; normal latency; low latency; lowest latency |
| `interface-clock-source-options-*` | automatic; internal |
| `interface-auto-power-save-options-*` | 30 min; OFF |
| `interface-link-line-options-*` | Disabled; Enabled |

## Menus and dialogs

| Prefix | Content |
| --- | --- |
| `menu-file-*` | Effect Reset; Mixer Reset; ADC Preset; ADC/DAC Preset; Save; Close |
| `menu-window-*` | Minimize |
| `dialog-effect-reset-*` | Effect Reset confirmation |
| `dialog-mixer-reset-*` | Mixer Reset confirmation |
| `dialog-adc-dac-preset-*` | ADC/DAC operation confirmation |
| `dialog-save-*` | Save-to-device confirmation |
| `dialog-adc-preset.jpg` | Observed ADC Preset menu activation; this action did not expose a separate confirmation window during capture |

All confirmation dialogs were dismissed with **Cancel/Escape**. No reset,
ADC/DAC preset, or save operation was accepted.

## Behavioral observations for the Linux panel

- Stereo Mix removes the Computer 3 and Computer 4 strips and disables all
  line/digital output-source choices except Master L and R.
- Entering Stereo Mix automatically selected Master L and R for line output.
  Returning to Multitrack did **not** restore the prior line-output choice; the
  original Computer 1 and 2 route had to be selected explicitly.
- The Interface option lists use native white combo-box popups rather than the
  metallic panel styling.
- Effects share a persistent Reverb section. The left section changes between
  Compressor, Noise Suppressor, De-esser, Exciter, EQ, and Limiter/Low-cut.
- File commands use native Windows confirmation dialogs with OK and Cancel.
- The capture began and ended with Analog 2 muted at minimum. Its fader was not
  adjusted.

