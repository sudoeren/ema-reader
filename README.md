<p align="center"><img src="static/logo.svg" width="96" alt=""></p>

# EMA Reader

Listen to books and articles in Turkish. EMA Reader turns an EPUB, a PDF, a text file or a web page into speech with the [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) model, fully on your own machine.

This is an unofficial project built on EMA Lightning; it is not affiliated with the model's author.

- **Reads as you follow:** the sentence being spoken is highlighted, and clicking any sentence jumps there.
- **Remembers your place** in every book.
- **Adjustable speed**, generated at that speed by the model rather than by speeding up the audio.
- **Downloads a chapter** as a WAV file to listen to elsewhere.
- **Offline:** no account, no API key, and no text or audio leaves the machine.

The model has a single voice and speaks Turkish only.

## Desktop app

For people who should not have to touch a terminal, EMA Reader is packaged as a desktop app: one download, a double click, and it opens in its own window. Everything it needs is inside, including the model, so it works without an internet connection. Books are kept in the user's data folder.

Installers are built by GitHub Actions for Windows (`EMA-Reader-Setup.exe`), macOS (`EMA-Reader.dmg`) and Linux (`EMA-Reader-linux.tar.gz`) whenever a version tag such as `v1.0.0` is pushed, and attached to that release.

To build it yourself, for the system you are on:

```bash
uv run build.py                      # writes dist/EMA Reader/
uv run --extra desktop desktop.py    # or run the window without packaging
```

The build uses a CPU-only PyTorch, because the model is fast enough without a GPU and the GPU libraries would add several gigabytes. The Linux build is about 500 MB compressed; much of that is PyTorch and the Qt window toolkit.

The installers are not code-signed, so Windows SmartScreen and macOS Gatekeeper warn before the first start.

## Run from source


Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run app.py
```

This opens the reader in the browser at `http://127.0.0.1:8000`.

The model weights (about 34 MB) are downloaded from Hugging Face on first run. After that the model loads from disk without touching the network; once a day a background check fetches newer weights, which are used from the next start. Set `HF_HUB_OFFLINE=1` to turn that check off.

## Use

Choose "Add a book or article", then drop a file, pick one, or paste the address of an article.

| Source | Chapters |
|---|---|
| EPUB | The book's own sections |
| PDF | The outline if the file has one, otherwise every 10 pages |
| Text, Markdown | `#` headings; a file without headings is one chapter |
| HTML file, web address | The article text as one chapter |

Scanned PDFs that contain only images have no text to read.

In the reader, `Space` plays and pauses, and `←` / `→` move one sentence. Media keys work too.

When run from source, books are stored as JSON in the `library/` folder next to the app.

`app.py` takes these options:

| Option | Description | Default |
|---|---|---|
| `--host` | Address to listen on; `0.0.0.0` exposes it to the network | 127.0.0.1 |
| `--port` | Port | 8000 |
| `--speed` | Speed for requests that do not set one, 0.25 to 4 | `$EMA_SPEED`, else 1.0 |
| `--cpu` | Use the CPU instead of the GPU | |
| `--lightning` | NVIDIA fast path; compiles at startup, which takes minutes | |
| `--no-browser` | Do not open the browser | |

There is no authentication; keep that in mind before using `--host 0.0.0.0`.

## HTTP API

The server behind the reader can be used on its own.

| Endpoint | Description |
|---|---|
| `GET /api/books` | The library |
| `POST /api/books?name=kitap.epub` | Add a file; the request body is the file |
| `POST /api/books` | Add an article: `{"url": "https://..."}` |
| `GET /api/books/ID` | One book with its text |
| `DELETE /api/books/ID` | Remove a book |
| `PUT /api/books/ID/progress` | `{"chapter": 0, "sentence": 12}` |
| `GET /api/books/ID/chapters/N/audio` | A chapter as one WAV file (24 kHz); takes `speed` |
| `GET /tts`, `POST /tts` | Plain text to speech |

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

Measured on an RTX 4050 Laptop GPU:

| | Time |
|---|---|
| One sentence on a warm model | about 20 ms |
| A 32-second chapter, exported | 0.45 s |
| The same sentence with `--lightning` | about 9 ms |
| `--lightning` startup compilation | about 2 minutes |

## License

The model and the `ema-lightning` package are licensed under Apache 2.0. Tell listeners that the audio is AI-generated.
