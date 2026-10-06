# Development

Everything technical about EMA Reader: how it is put together, how to run it from source, its HTTP API, the command-line tool, and how the installers are built.

## Layout

| File | What it does |
|---|---|
| `app.py` | The server: the library, speech, exports, and the page itself |
| `extract.py` | Turns EPUB, PDF, text, Markdown and web pages into chapters of sentences, with cover and details |
| `export.py` | Writes a chapter or a book as MP3, OGG, Opus, FLAC, WAV or text |
| `ema.py` | Loads the model; also a command-line tool that speaks text |
| `desktop.py` | The desktop window around the server |
| `build.py` | Builds the self-contained app for Windows and macOS |
| `static/index.html` | The whole interface: one page, no build step |
| `tests/` | Tests for the parts that do not need the model |

The model is [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning): 8.6M parameters, about 34 MB, Turkish only, one voice. Its weights are downloaded from Hugging Face on first run. After that the model loads from disk without touching the network; once a day a background check fetches newer weights, which are used from the next start. Set `HF_HUB_OFFLINE=1` to turn that check off.

## Run from source

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run app.py                         # the reader in the browser, at http://127.0.0.1:8000
uv run --extra desktop desktop.py     # the reader in its own window
```

| `app.py` option | Description | Default |
|---|---|---|
| `--host` | Address to listen on; `0.0.0.0` exposes it to the network | 127.0.0.1 |
| `--port` | Port | 8000 |
| `--speed` | Speed for requests that do not set one, 0.25 to 4 | `$EMA_SPEED`, else 1.0 |
| `--cpu` | Use the CPU instead of the GPU | |
| `--lightning` | NVIDIA fast path; compiles at startup, which takes minutes | |
| `--no-browser` | Do not open the browser | |

There is no authentication; keep that in mind before using `--host 0.0.0.0`.

From source, books are stored as JSON in `library/` next to the code. The desktop app keeps them in the user's data folder instead. `EMA_READER_LIBRARY` overrides either.

Opening the page with `?tour` at the end of the address replays the first-run tour.

## The desktop window

`desktop.py` starts the server on a local port and shows the page in a native window.

- **Linux:** GTK 4 and libadwaita, with the app's buttons in the header bar. It needs `gtk4`, `libadwaita` and `webkitgtk-6.0` from the system. The page and the window talk over a WebKit message handler: the page says what is on screen and which theme it uses, the window sends button presses back.
- **Windows and macOS:** the system's web view through pywebview, with the page's own top bar.

```bash
uv run --extra desktop desktop.py kitap.epub     # add a file and open it
uv run --extra desktop desktop.py --install      # Linux: add to the applications menu; --uninstall removes it
uv run --extra desktop desktop.py --check        # start without a window, make one sentence, exit
```

## Building the installers

```bash
uv run build.py        # on Windows or macOS; writes dist/EMA Reader/
```

The build is a PyInstaller folder with Python, a CPU-only PyTorch and the model weights inside, so the app starts without a download. The GPU build of PyTorch would add several gigabytes, and the model is fast enough on a CPU.

`.github/workflows/build.yml` runs the build on Windows and macOS whenever a version tag such as `v1.0.0` is pushed, wraps it in an installer (`EMA-Reader-Setup.exe`, made with `packaging/windows.iss`) and a disk image (`EMA-Reader.dmg`), and attaches both to the release. It can also be started by hand from the Actions tab.

The installers are not code-signed, so Windows SmartScreen and macOS Gatekeeper warn before the first start.

## Tests

```bash
uv run --with pytest pytest
```

The tests cover text extraction and export naming and do not load the model. `.github/workflows/test.yml` runs them on every push.

## HTTP API

| Endpoint | Description |
|---|---|
| `GET /api/books` | The library |
| `POST /api/books?name=kitap.epub` | Add a file; the request body is the file |
| `POST /api/books` | Add an article: `{"url": "https://..."}` |
| `GET /api/books/ID` | One book with its text and details |
| `DELETE /api/books/ID` | Remove a book |
| `PUT /api/books/ID/progress` | `{"chapter": 0, "sentence": 12}` |
| `GET /api/books/ID/cover` | The cover picture, if the book has one |
| `POST /api/books/ID/export` | Start an export; returns `{"job": "..."}` |
| `GET /api/exports/JOB` | `{"state": "working", "progress": 0.4, "name": "..."}` |
| `GET /api/exports/JOB/file` | The finished file |
| `DELETE /api/exports/JOB` | Cancel an export |
| `GET /tts`, `POST /tts` | Plain text to speech |
| `GET /health` | `{"status": "ok", "version": "..."}` |

An export takes `scope` (`chapter` or `book`), `chapter` (its index), `format` (`mp3`, `ogg`, `opus`, `flac`, `wav` or `txt`), `split` (a ZIP with one file per chapter) and `speed`. The lossy formats are written at 24 kHz and the lossless ones at 48 kHz.

`/tts` takes its parameters in the query string or in a JSON body:

| Parameter | Description |
|---|---|
| `text` | Text to speak (required) |
| `speed` | 0.25 to 4; defaults to the server's `--speed` |
| `seed` | Non-negative integer; the same seed gives the same audio |
| `sample_rate` | 48000, 24000, 16000, 8000 |
| `stream` | If `true`, audio is sent as it is generated |

The response is a WAV file (16-bit, mono); the seed that was used is returned in the `X-Seed` header. With `stream=true` the response is headerless raw PCM (16-bit, little-endian, mono), the sample rate is in the `X-Sample-Rate` header, and the body ends when the connection closes. Invalid requests return `400` with `{"error": "..."}`.

```bash
curl "localhost:8000/tts?text=Merhaba" -o merhaba.wav
curl localhost:8000/tts -d '{"text": "Siparişiniz yola çıktı.", "speed": 1.2}' -o siparis.wav
curl -X POST --data-binary @kitap.epub "localhost:8000/api/books?name=kitap.epub"
```

## Command line

`ema.py` speaks text straight from the terminal, without the reader.

```bash
uv run ema.py "Merhaba dünya"              # play through the speakers
uv run ema.py "Merhaba" -o merhaba.wav     # write to a file
uv run ema.py -f text.txt -o clips         # one clip per line: clips/0.wav, 1.wav, ...
echo "Merhaba" | uv run ema.py             # read from stdin
uv run ema.py                              # interactive mode: type, Enter, listen
```

Playing through the speakers needs PortAudio installed on the system.

| Option | Description | Default |
|---|---|---|
| `-f FILE` | Text file; each line is spoken separately | |
| `-o PATH` | Write instead of playing: a `.wav` for one text, a folder for several lines | |
| `--speed` | Speaking speed, 0.25 to 4; below 1 is slower | `$EMA_SPEED`, else 1.0 |
| `--seed` | The same seed gives the same audio | random |
| `--rate` | Sample rate: 48000, 24000, 16000, 8000 | 48000 |
| `--api URL` | Use a running `app.py` instead of loading the model | `$EMA_API` |
| `--cpu` | Use the CPU instead of the GPU | |
| `--lightning` | NVIDIA fast path; compiles at startup, which takes minutes | |

In interactive mode, `/speed 0.8` changes the speed for the following texts, `Ctrl+C` stops the audio that is playing and `Ctrl+D` exits.

Every call loads the model from scratch, which takes about 3 seconds. With `app.py` running, `--api http://127.0.0.1:8000` (or `export EMA_API=...`) skips that and answers in about 0.2 seconds.

## Speed

Measured on a laptop with an RTX 4050 and a 16-core CPU:

| | Time |
|---|---|
| One sentence on a warm model, GPU | about 20 ms |
| A 5-second sentence on the CPU | about 0.3 s |
| A 34-minute chapter exported to MP3, GPU | 25 s |
| The desktop window, ready to use | about 2 s |
