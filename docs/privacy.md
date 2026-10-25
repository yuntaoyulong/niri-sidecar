# Privacy and data flow

Niri Sidecar has no telemetry, analytics endpoint, account service or automatic update checker. Its network operation is OpenSSH to the destinations selected by your interactive SSH clients, including the proxy/jump configuration you already use. Opening a pinned link explicitly may launch your browser.

## What each module reads

| Module | Input | Retention / destination |
| --- | --- | --- |
| Remote resources | This user's interactive `ssh` process arguments; selected `/proc`, cgroup and `df` values; NVIDIA metrics | Metrics stay in process memory and stdout. A private per-user SSH control socket lasts briefly after sampling. No remote daemon or metrics file is installed. |
| Window selectors | Niri window IDs, titles, app IDs and workspaces | Local in-memory list. No Codex session logs, prompts, auth files or conversation database are read. “Running” is a title-spinner heuristic. |
| Live previews | Requested windows via Niri's screencast API and PipeWire | Optional, disabled by default. Frames are kept in memory; streams stop when the preview hides. No screenshot/history directory is created. |
| File pins | Clipboard MIME types; file references when copied or explicitly pinned | Private local SQLite metadata and explicitly saved payloads. File contents are not duplicated for URI pins. |
| Folder parking | Nautilus window titles and GTK window IDs | Optional local session D-Bus interface. No file index, upload or directory history is maintained by the hook. |
| Theme | DMS settings/palette when present | Read locally. Fixed default colours work without DMS. |

OpenSSH handles credentials. The program does not parse private-key files, copy your SSH configuration into its package, or store passwords. Polling forces batch mode, strict host-key checking, no new forwarding, no agent forwarding and no local-command execution. Your own configured ProxyCommand and SSH Match rules remain part of the SSH trust model.

`privacy.redact_hosts` is on by default: usernames, SSH destination labels and remote hostnames are replaced in the resource UI/JSON. GPU/CPU models, mount paths, local file names and window titles are not anonymised. Turning host redaction off exposes those addresses locally; it still does not upload them.

Window titles, filenames and metric labels are rendered as plain text. Qt’s default auto-rich-text detection can load images from markup, so Sidecar explicitly disables it for these fields; see the [Qt Text documentation](https://doc.qt.io/qt-6/qml-qtquick-text.html).

## Local paths

- Configuration: `$XDG_CONFIG_HOME/niri-sidecar/config.json` (normally `~/.config/...`).
- Explicit file/clipboard pins: `$XDG_STATE_HOME/niri-sidecar/pins`, directory mode `0700`, restrictive creation umask.
- Remote multiplexed sockets: `$XDG_RUNTIME_DIR/niri-sidecar/ssh`, directory mode `0700`.
- Preview socket: `$XDG_RUNTIME_DIR/niri-sidecar-preview/control.sock`, directory `0700`, socket `0600`.
- Temporary pin cards: `$XDG_RUNTIME_DIR/niri-sidecar-cards` (private per-user fallback if runtime directory is unavailable).
- Service errors: local user journal. Do not paste unreviewed errors, raw SSH invocations or runtime JSON into public issues.

Removing a pin deletes its saved metadata/payload; it does not delete the original file. Uninstall preserves configuration and explicit pins, so the user can decide whether to remove them. To remove those records too, stop Sidecar and remove **its** `niri-sidecar` config/state directories. Do not delete another program's clipboard history or SSH files.

## Demonstrations and releases

`niri-sidecar demo` is a separate path using the committed synthetic fixture. It does not discover live SSH processes, read a clipboard payload or fetch the real window list. Its fake focus/pin actions do not operate on real windows/files. The overview SVG is a labelled illustration, not a screenshot of the maintainer's desktop.

Only source, examples, tests and documentation belong in releases. `.gitignore` excludes runtime databases, logs, binary hooks and local configuration. Tests reject workstation home paths and common key/token formats. Gitleaks is run on the release tree/history before publication. These checks reduce accidental disclosure; they do not anonymise arbitrary screenshots or issue attachments submitted later.

Report a suspected credential or data exposure privately via GitHub's security reporting feature. Do not include a live secret in a public issue.
