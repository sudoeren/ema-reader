# ema

[EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) Türkçe metin okuma modeli için minimal bir CLI ve HTTP API.

Model 8.6M parametre (yaklaşık 34 MB), tamamen yerelde çalışır. Tek bir sesi vardır ve yalnızca Türkçe okur.

## Kurulum

[uv](https://docs.astral.sh/uv/) gerekir. Hoparlörden çalmak için sistemde PortAudio kurulu olmalı.

```bash
uv sync
```

Model ağırlıkları ilk çalıştırmada Hugging Face'ten iner.

## CLI

```bash
uv run ema.py "Merhaba dünya"              # hoparlörden çal
uv run ema.py "Merhaba" -o merhaba.wav     # dosyaya yaz
uv run ema.py -f metin.txt                 # dosyayı satır satır oku
uv run ema.py -f metin.txt -o klipler      # her satır ayrı klip: klipler/0.wav, 1.wav, ...
echo "Merhaba" | uv run ema.py             # stdin'den oku
uv run ema.py                              # etkileşimli mod: yaz, Enter, dinle
```

| Seçenek | Açıklama | Varsayılan |
|---|---|---|
| `-f DOSYA` | Metin dosyası; her satır ayrı seslendirilir | |
| `-o YOL` | Çalmak yerine yaz: tek metin için `.wav`, çok satır için klasör | |
| `--speed` | Konuşma hızı, 0.25 ile 4 arası | 1.0 |
| `--seed` | Aynı seed aynı sesi verir | rastgele |
| `--rate` | Örnekleme hızı: 48000, 24000, 16000, 8000 | 48000 |
| `--api URL` | Modeli yüklemek yerine açık duran API'yi kullan | `$EMA_API` |
| `--cpu` | GPU yerine CPU kullan | |
| `--lightning` | NVIDIA hızlı yolu; açılışta dakikalar süren derleme yapar | |

Etkileşimli modda `Ctrl+C` çalan sesi keser, `Ctrl+D` çıkar.

## API

```bash
uv run api.py                    # http://127.0.0.1:8000
uv run api.py --host 0.0.0.0 --port 9000
```

Model bir kez yüklenir ve sıcak kalır. Seçenekler: `--host`, `--port`, `--cpu`, `--lightning`.

| Uç nokta | Açıklama |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /tts?text=...` | Parametreler sorgu dizgisinde |
| `POST /tts` | Parametreler JSON gövdede |

| Parametre | Açıklama |
|---|---|
| `text` | Seslendirilecek metin (zorunlu) |
| `speed` | 0.25 ile 4 arası |
| `seed` | Negatif olmayan tam sayı |
| `sample_rate` | 48000, 24000, 16000, 8000 |
| `stream` | `true` ise ses üretildikçe akar |

Yanıt bir WAV dosyasıdır (16 bit, mono); kullanılan seed `X-Seed` başlığında döner. `stream=true` ile yanıt başlıksız ham PCM'dir (16 bit, little-endian, mono), örnekleme hızı `X-Sample-Rate` başlığındadır ve gövde bağlantı kapanınca biter. Geçersiz istekler `400` ve `{"error": "..."}` döner.

```bash
curl "localhost:8000/tts?text=Merhaba" -o merhaba.wav
curl localhost:8000/tts -d '{"text": "Siparişiniz yola çıktı.", "speed": 1.2}' -o siparis.wav

# üretilirken dinle
curl -s localhost:8000/tts -d '{"text": "Bu ses üretilirken akıyor.", "stream": true}' \
  | ffplay -f s16le -ar 48000 -nodisp -autoexit -
```

```python
import requests

wav = requests.post("http://127.0.0.1:8000/tts", json={"text": "Merhaba"}).content
open("merhaba.wav", "wb").write(wav)
```

Kimlik doğrulama yoktur; `--host 0.0.0.0` ile ağa açmadan önce bunu hesaba katın.

### CLI'ı API üzerinden kullanmak

Her CLI çağrısı modeli baştan yükler. API açıkken CLI'ı ona bağlarsanız bu bekleme kalkar:

```bash
export EMA_API=http://127.0.0.1:8000
uv run ema.py "Merhaba"
```

## Hız

RTX 4050 Laptop GPU üzerinde ölçüldü:

| | Süre |
|---|---|
| Tek seferlik CLI çağrısı, dosyaya (model yükleme dahil) | 2,8 sn |
| Aynı çağrı, `--api` ile | 0,2 sn |
| Isınmış modelde bir cümle üretimi | yaklaşık 20 ms |
| Aynısı `--lightning` ile | yaklaşık 9 ms |
| `--lightning` açılış derlemesi | yaklaşık 2 dakika |

## Lisans

Model ve `ema-lightning` paketi Apache 2.0 lisanslıdır. Üretilen sesin yapay zekâ ile üretildiğini dinleyenlere belirtin.
