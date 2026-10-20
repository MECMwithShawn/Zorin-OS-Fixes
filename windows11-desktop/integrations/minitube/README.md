# Axentra Mini Media system EQ

Run `python3 integrate.py /path/to/minitube` against the existing Rust/GTK source, then rebuild and install that player using its normal build environment. The integrator adds a common panel after the appearance controls, preserves unrelated source and rejects changed insertion points. It is idempotent. The desktop companion with `audio_effects.py`, `audio_spectrum.py` and `audio-presets.json` must already be installed in `~/.local/share/zorin11-hub`.

The panel offers the system's eight presets, synchronized with Sound settings, a link to those settings, and sixteen playback-frequency bars. Choices affect system playback and persist across sign-in. It does not add automatic track classification or duplicate the DSP in the player. Hidden/minimized controls release the monitor process; the microphone is never used. Missing desktop helpers disable selection.

For the native test, copy `test_widget.rs` to the player's `examples/system_eq_test.rs`, build that example, then run `python3 test_widget.py /path/to/system_eq_test`. It runs under private Xvfb, D-Bus and XDG directories with controlled helper processes and does not change host audio settings.
