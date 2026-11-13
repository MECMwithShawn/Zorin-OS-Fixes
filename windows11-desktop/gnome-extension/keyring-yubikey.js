// A YubiKey touch for GNOME's own "Unlock Keyring" prompt.
//
// After auto-login the keyrings are locked, and whichever app asks first gets
// GNOME's password prompt. When YubiKey keyring unlock is set up
// (yubikey/keyring_unlock.py setup), this asks keyring_unlock.py for the
// keyring's sealed password while the prompt shows: the key blinks, a touch
// fills the password in and the prompt completes. Typing the password still
// works, and closing the prompt stops the helper. Each keyring is tried once
// per prompt, so a stale saved password falls back to typing.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';

const helperPath = () => GLib.getenv('ZORIN11_YUBIKEY_HELPER') ||
    GLib.build_filenamev([GLib.get_user_data_dir(), 'zorin11-hub', 'yubikey', 'keyring_unlock.py']);
const configPath = () => GLib.build_filenamev([GLib.get_user_config_dir(), 'zorin11-hub', 'yubikey-keyring.json']);

const HINT = 'Touch your YubiKey to unlock, or type the password.';
const RETRY = 'The YubiKey’s saved password didn’t work. Type the password.';

export class KeyringYubiKey {
    constructor() {
        this._prompts = new Map();
        // Every keyring prompt hands its password entry over right after it's made: attach there.
        // (The prompter's 'prompting' changes before the prompt exists, and 'new-prompt' stops at
        // the Shell's own handler.)
        const self = this;
        this._injections = new InjectionManager();
        this._injections.overrideMethod(Shell.KeyringPrompt.prototype, 'set_password_actor',
            original => function (actor) {
                original.call(this, actor);
                if (actor)
                    self._attach(this);
            });
        // A prompt that was already showing when the extension started.
        const prompter = Main.componentManager?._allComponents?.keyring;
        if (prompter?.prompting && prompter._currentPrompt?.get_password_actor?.())
            this._attach(prompter._currentPrompt);
    }

    get ready() {
        return !!this._injections;
    }

    _attach(prompt) {
        if (this._prompts.has(prompt))
            return;
        const state = {ids: [], tried: new Set(), helper: null, hint: null};
        this._prompts.set(prompt, state);
        state.ids.push(prompt.connect('show-password', () => this._start(prompt)));
        state.ids.push(prompt.connect('prompt-close', () => this._detach(prompt)));
        if (prompt.password_visible)
            this._start(prompt);
    }

    _start(prompt) {
        const state = this._prompts.get(prompt);
        if (!state || state.helper || prompt.password_new || prompt.confirm_visible)
            return;
        const description = prompt.description ?? '';
        if (state.tried.has(description)) {
            // gnome-keyring asks again after a wrong password: leave it to typing.
            this._hint(prompt, state, RETRY);
            return;
        }
        if (!GLib.file_test(configPath(), GLib.FileTest.EXISTS))
            return;
        state.tried.add(description);
        let helper;
        try {
            helper = Gio.Subprocess.new(['/usr/bin/python3', helperPath(), 'password', '--prompt', description],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
        } catch (e) {
            logError(e, 'zorin11 YubiKey keyring');
            return;
        }
        state.helper = helper;
        this._hint(prompt, state, HINT);
        helper.communicate_async(null, null, (proc, result) => {
            let bytes = null;
            try {
                [, bytes] = proc.communicate_finish(result);
            } catch (e) {}
            if (state.helper !== proc)
                return;  // the prompt closed meanwhile
            state.helper = null;
            const secret = proc.get_if_exited() && proc.get_exit_status() === 0 && bytes?.get_size()
                ? new TextDecoder().decode(bytes.toArray()) : null;
            if (!secret) {
                this._hint(prompt, state, null);  // not ours, or the key failed: type it
                return;
            }
            const actor = prompt.get_password_actor();
            if (!actor || !prompt.password_visible)
                return;
            actor.text = secret;
            prompt.complete();
        });
    }

    _hint(prompt, state, text) {
        if (!text) {
            const hint = state.hint;
            state.hint = null;
            hint?.destroy();
            return;
        }
        if (!state.hint) {
            const entry = prompt.get_password_actor()?.get_parent();
            const box = entry?.get_parent();
            if (!box)
                return;
            state.hint = new St.Label({style_class: 'prompt-dialog-info-label', x_align: Clutter.ActorAlign.CENTER});
            state.hint.clutter_text.line_wrap = true;
            box.insert_child_above(state.hint, entry);
            const hint = state.hint;
            hint.connect('destroy', () => {
                if (state.hint === hint)
                    state.hint = null;
            });
        }
        state.hint.text = text;
    }

    _detach(prompt) {
        const state = this._prompts.get(prompt);
        if (!state)
            return;
        this._prompts.delete(prompt);
        for (const id of state.ids) {
            try {
                prompt.disconnect(id);
            } catch (e) {}
        }
        // SIGTERM: the helper cancels the key's blink and exits.
        state.helper?.send_signal(15);
        state.helper = null;
        const hint = state.hint;
        state.hint = null;
        try {
            hint?.destroy();
        } catch (e) {}
    }

    destroy() {
        this._injections?.clear();
        this._injections = null;
        for (const prompt of [...this._prompts.keys()])
            this._detach(prompt);
    }
}
