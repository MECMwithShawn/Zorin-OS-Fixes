# Axentra SnippingTool feature coverage

Reference: [Microsoft's Windows 11 Snipping Tool guide](https://support.microsoft.com/en-us/windows/apps/use-snipping-tool-to-capture-screenshots), checked 2026-10-20. Axentra is an independent Linux implementation in Rust/GTK; it does not bundle Microsoft binaries, assets or AI models.

The window layout follows the [Windows 11 example on Computer Hope](https://www.computerhope.com/jargon/s/snipping.htm#win11), using the desktop's dark appearance: a compact initial window, left-aligned title, New / capture mode / delay command bar and centered shortcut hint. A video-mode button retains the newer recording workflow. Opening or capturing an image expands the window and reveals one icon toolbar with accessible names/tooltips. Shapes, emoji, manual redaction, image color picking and rotation are under **More tools**; ink color and thickness are under **Ink settings**. Save, Copy and Share remain directly available in the editor. **⋯ → Open image** and Ctrl+O open existing files.

| Guide workflow | Axentra behavior |
|---|---|
| Rectangle, freeform, window, full-screen snips | All four on X11; Wayland delegates selection to the desktop screenshot portal. |
| Delay / capture an open menu | 0–5 or 10 seconds, cancellable. |
| Win+Shift+S | Reversible custom screenshot shortcut, preserving existing bindings. |
| Video snip / Win+Shift+R | Rectangle on X11 → H.264/AAC MP4; screen/window through Wayland ScreenCast consent → VP8/Opus WebM. Press shortcut again or Stop recording to finish. X11 recording has a two-hour limit. |
| Recording audio | Playback and microphone are separate, explicit opt-ins for each recording. Both default off. |
| Pen, highlighter, shapes, emoji | Native annotation tools; eraser removes annotations while retaining screenshot pixels. |
| Crop, undo/redo | Raster crop, twenty-step history; clockwise rotation and Fit/100/200/400% zoom also included. |
| Text actions | Local Tesseract OCR; select/copy text or copy all. Installer includes English data; recognition depends on the installed Tesseract language data. |
| Quick redact | Detects email addresses and likely phone numbers; manual rectangular redaction is also available. Saved/shared images contain flattened pixels. Review for OCR misses; original auto-saved screenshots and undo history still contain the original content. |
| Automatic screenshot saving | On by default, alongside auto-copy. Settings changes these and the folder. Originals are saved once; edits require Save as. Videos require explicit saving. |
| Save / clipboard | PNG and JPEG images, image clipboard, native overwrite confirmation; MP4/WebM video saving. |
| Color picker | Image-pixel HEX sampling and the desktop's permission-mediated screen color picker. |
| Perfect screenshot | Copilot-specific content-aware framing is not provided. Manual selection and crop remain available. |
| Share / edit in Paint / edit in Clipchamp | Native application chooser opens a rendered copy or recording in a selected installed app. Paint and Clipchamp are Microsoft applications and are not bundled. |
| Print | Native GTK print dialog; user chooses printer or Print to File. |
| Keyboard | Ctrl+N/O/S/C/Z, Ctrl+Shift+Z, Ctrl+P; Alt+N/M/D for capture/mode/delay; arrows move rectangle selection, Shift+arrows resize, Enter accepts, Escape cancels. Ctrl+Shift+R stops recording when focused. Existing PrintScreen behavior is retained. |
| Pin to taskbar | Use the existing GNOME/Start pin action on the installed desktop entry. |

Capture, OCR and encoding stay local. Temporary OCR/recording/export files use private cache directories. No persistent screen-sharing permission is requested. Wayland's portal controls available screenshot/recording sources; rectangular video crops are currently X11-only. Portal denial keeps the previous image/clip. Recording processes receive a termination signal if the app exits unexpectedly.

## Validation

Run `cargo test --locked` under Xvfb for raster/history/OCR-parser checks. `test_live.py` exercises the compact initial window, contextual editing toolbar, mode menu, native capture/edit/save/clipboard and the screenshot portal. `test_features_live.py` tests actual Tesseract, redaction pixels, erasing, emoji, color picker, settings, keyboard capture, native dialog cancellation, video overwrite protection and real FFmpeg video, including tools selected from the new popover. `test_recording_portal.py` uses a private ScreenCast service, actual PipeWire/GStreamer video and virtual audio devices to verify consent requests, descriptor transfer, encoded video/audio, cleanup, compositor-side termination and denial. It tests the protocol and media path rather than a live Wayland compositor's picker.
