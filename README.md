# ema

A minimal CLI and HTTP API for the [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) Turkish text-to-speech model.

The model has 8.6M parameters (about 34 MB) and runs fully offline. It has a single voice and speaks Turkish only.

## Install

Requires [uv](https://docs.astral.sh/uv/). Playing through the speakers needs PortAudio installed on the system.

```bash
uv sync
```

The model weights are downloaded from Hugging Face on first run. After that the model loads from disk without touching the network; once a day a background check fetches newer weights, which are used from the next start. Set `HF_HUB_OFFLINE=1` to turn that check off.

## CLI

```bash
uv run ema.py "Merhaba dünya"              # play through the speakers
uv run ema.py "Merhaba" -o merhaba.wav     # write to a file
uv run ema.py -f text.txt                  # read a file line by line
uv run ema.py -f text.txt -o clips         # one clip per line: clips/0.wav, 1.wav, ...
echo "Merhaba" | uv run ema.py             # read from stdin
uv run ema.py                              # interactive mode: type, Enter, listen
```

| Option | Description | Default |
|---|---|---|
| `-f FILE` | Text file; each line is spoken separately | |
| `-o PATH` | Write instead of playing: a `.wav` for one text, a folder for several lines | |
| `--speed` | Speaking speed, 0.25 to 4 | 1.0 |
| `--seed` | The same seed gives the same audio | random |
| `--rate` | Sample rate: 48000, 24000, 16000, 8000 | 48000 |
| `--api URL` | Use a running API instead of loading the model | `$EMA_API` |
| `--cpu` | Use the CPU instead of the GPU | |
| `--lightning` | NVIDIA fast path; compiles at startup, which takes minutes | |

In interactive mode, `Ctrl+C` stops the audio that is playing and `Ctrl+D` exits.

## API

```bash
uv run api.py                    # http://127.0.0.1:8000
uv run api.py --host 0.0.0.0 --port 9000
```

The model is loaded once and kept warm. Options: `--host`, `--port`, `--cpu`, `--lightning`.

| Endpoint | Description |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /tts?text=...` | Parameters in the query string |
| `POST /tts` | Parameters in a JSON body |

| Parameter | Description |
|---|---|
| `text` | Text to speak (required) |
| `speed` | 0.25 to 4 |
| `seed` | Non-negative integer |
| `sample_rate` | 48000, 24000, 16000, 8000 |
| `stream` | If `true`, audio is sent as it is generated |

The response is a WAV file (16-bit, mono); the seed that was used is returned in the `X-Seed` header. With `stream=true` the response is headerless raw PCM (16-bit, little-endian, mono), the sample rate is in the `X-Sample-Rate` header, and the body ends when the connection closes. Invalid requests return `400` with `{"error": "..."}`.

```bash
curl "localhost:8000/tts?text=Merhaba" -o merhaba.wav
curl localhost:8000/tts -d '{"text": "Siparişiniz yola çıktı.", "speed": 1.2}' -o siparis.wav

# listen while it is being generated
curl -s localhost:8000/tts -d '{"text": "Bu ses üretilirken akıyor.", "stream": true}' \
  | ffplay -f s16le -ar 48000 -nodisp -autoexit -
```

```python
import requests

wav = requests.post("http://127.0.0.1:8000/tts", json={"text": "Merhaba"}).content
open("merhaba.wav", "wb").write(wav)
```

There is no authentication; keep that in mind before exposing it to the network with `--host 0.0.0.0`.

### Using the CLI through the API

Every CLI call loads the model from scratch. Pointing the CLI at a running API removes that wait:

```bash
export EMA_API=http://127.0.0.1:8000
uv run ema.py "Merhaba"
```

## Speed

Measured on an RTX 4050 Laptop GPU:

| | Time |
|---|---|
| One-off CLI call, to a file (including model load) | 2.8 s |
| The same call with `--api` | 0.2 s |
| One sentence on a warm model | about 20 ms |
| The same with `--lightning` | about 9 ms |
| `--lightning` startup compilation | about 2 minutes |

## License

The model and the `ema-lightning` package are licensed under Apache 2.0. Tell listeners that the audio is AI-generated.
