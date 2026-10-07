# Geliştirme

EMA Reader'ın teknik tarafı: nasıl kurulduğu, kaynaktan nasıl çalıştırıldığı, HTTP API'si, komut satırı aracı ve kurulum dosyalarının nasıl üretildiği.

## Düzen

| Dosya | Ne yapar |
|---|---|
| `app.py` | Sunucu: kitaplık, seslendirme, dışa aktarım ve sayfanın kendisi |
| `extract.py` | EPUB, PDF, metin, Markdown ve web sayfalarını kapak ve ayrıntılarıyla birlikte cümlelerden oluşan bölümlere çevirir |
| `export.py` | Bir bölümü ya da kitabı MP3, OGG, Opus, FLAC, WAV veya metin olarak yazar |
| `ema.py` | Modeli yükler; ayrıca metni seslendiren bir komut satırı aracıdır |
| `desktop.py` | Sunucunun çevresindeki masaüstü penceresi |
| `build.py` | Windows ve macOS için kendi kendine yeten uygulamayı üretir |
| `static/index.html` | Arayüzün tamamı: tek sayfa, derleme adımı yok |
| `tests/` | Model gerektirmeyen kısımların testleri |

Model [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning)'dir: 8,6 milyon parametre, yaklaşık 34 MB, yalnızca Türkçe, tek ses. Ağırlıkları ilk çalıştırmada Hugging Face'ten indirilir. Sonrasında model ağa dokunmadan diskten yüklenir; günde bir kez arka planda yeni ağırlık olup olmadığına bakılır ve varsa bir sonraki açılışta kullanılır. Bu denetimi kapatmak için `HF_HUB_OFFLINE=1` ayarla.

Uygulama yalnızca Türkçedir: model başka dil konuşmadığı için arayüz, sunucunun hata iletileri ve komut satırı çıktıları da Türkçe yazılır. Kodun kendisi (adlar ve yorumlar) İngilizcedir.

## Kaynaktan çalıştırma

[uv](https://docs.astral.sh/uv/) gerekir.

```bash
uv sync
uv run app.py                         # okuyucu tarayıcıda, http://127.0.0.1:8000 adresinde
uv run --extra desktop desktop.py     # okuyucu kendi penceresinde
```

| `app.py` seçeneği | Açıklama | Varsayılan |
|---|---|---|
| `--host` | Dinlenecek adres; `0.0.0.0` ağa açar | 127.0.0.1 |
| `--port` | Port | 8000 |
| `--speed` | Hız belirtmeyen istekler için hız, 0.25 ile 4 arası | `$EMA_SPEED`, yoksa 1.0 |
| `--cpu` | GPU yerine CPU kullan | |
| `--lightning` | NVIDIA hızlı yolu; açılışta derlenir, bu dakikalar sürer | |
| `--no-browser` | Tarayıcıyı açma | |

Kimlik doğrulama yoktur; `--host 0.0.0.0` kullanmadan önce bunu aklında tut.

Kaynaktan çalışırken kitaplar kodun yanındaki `library/` klasöründe JSON olarak saklanır. Masaüstü uygulaması ise onları kullanıcının veri klasöründe tutar. `EMA_READER_LIBRARY` ikisini de geçersiz kılar.

Sayfayı adresin sonuna `?tour` ekleyerek açmak, ilk açılıştaki tanıtımı yeniden oynatır.

## Masaüstü penceresi

`desktop.py`, sunucuyu yerel bir portta başlatır ve sayfayı yerel bir pencerede gösterir.

- **Linux:** GTK 4 ve libadwaita; uygulamanın düğmeleri başlık çubuğundadır. Sistemde `gtk4`, `libadwaita` ve `webkitgtk-6.0` bulunmalıdır. Sayfa ile pencere bir WebKit ileti işleyicisi üzerinden konuşur: sayfa ekranda ne olduğunu ve hangi temayı kullandığını söyler, pencere de düğme basışlarını geri gönderir.
- **Windows ve macOS:** pywebview aracılığıyla sistemin web görünümü; sayfanın kendi üst çubuğuyla.

```bash
uv run --extra desktop desktop.py kitap.epub     # bir dosya ekle ve aç
uv run --extra desktop desktop.py --install      # Linux: uygulamalar menüsüne ekle; --uninstall kaldırır
uv run --extra desktop desktop.py --check        # penceresiz başlat, bir cümle üret, çık
```

## Kurulum dosyalarını üretme

```bash
uv run build.py        # Windows ya da macOS'te; dist/EMA Reader/ klasörünü yazar
```

Çıktı; içinde Python, yalnızca CPU'lu bir PyTorch ve model ağırlıkları bulunan bir PyInstaller klasörüdür, bu yüzden uygulama indirme yapmadan açılır. PyTorch'un GPU'lu sürümü birkaç gigabayt eklerdi; model CPU'da da yeterince hızlıdır.

`.github/workflows/build.yml`, `v1.0.0` gibi bir sürüm etiketi gönderildiğinde derlemeyi Windows ve macOS'te çalıştırır, bir kurulum dosyasına (`EMA-Reader-Setup.exe`, `packaging/windows.iss` ile üretilir) ve bir disk görüntüsüne (`EMA-Reader.dmg`) sarar, ikisini de sürüme ekler. Actions sekmesinden elle de başlatılabilir.

Kurulum dosyaları kod imzalı değildir; bu yüzden Windows SmartScreen ve macOS Gatekeeper ilk açılıştan önce uyarır.

## Testler

```bash
uv run --with pytest pytest
```

Testler metin çıkarmayı ve dışa aktarım adlandırmasını kapsar, modeli yüklemez. `.github/workflows/test.yml` onları her gönderimde çalıştırır.

## HTTP API

| Uç nokta | Açıklama |
|---|---|
| `GET /api/books` | Kitaplık |
| `POST /api/books?name=kitap.epub` | Dosya ekle; isteğin gövdesi dosyanın kendisidir |
| `POST /api/books` | Makale ekle: `{"url": "https://..."}` |
| `GET /api/books/ID` | Metni ve ayrıntılarıyla tek bir kitap |
| `DELETE /api/books/ID` | Kitabı kaldır |
| `PUT /api/books/ID/progress` | `{"chapter": 0, "sentence": 12}` |
| `GET /api/books/ID/cover` | Kitabın kapağı varsa kapak resmi |
| `POST /api/books/ID/export` | Dışa aktarımı başlat; `{"job": "..."}` döner |
| `GET /api/exports/JOB` | `{"state": "working", "progress": 0.4, "name": "..."}` |
| `GET /api/exports/JOB/file` | Hazır dosya |
| `DELETE /api/exports/JOB` | Dışa aktarımı iptal et |
| `GET /tts`, `POST /tts` | Düz metinden sese |
| `GET /health` | `{"status": "ok", "version": "..."}` |

Dışa aktarım şunları alır: `scope` (`chapter` ya da `book`), `chapter` (bölümün sırası), `format` (`mp3`, `ogg`, `opus`, `flac`, `wav` ya da `txt`), `split` (her bölüm için ayrı dosya içeren bir ZIP) ve `speed`. Kayıplı biçimler 24 kHz, kayıpsız olanlar 48 kHz olarak yazılır.

`/tts`, parametrelerini sorgu dizgisinden ya da JSON gövdesinden alır:

| Parametre | Açıklama |
|---|---|
| `text` | Seslendirilecek metin (zorunlu) |
| `speed` | 0.25 ile 4 arası; varsayılanı sunucunun `--speed` değeridir |
| `seed` | Negatif olmayan tam sayı; aynı seed aynı sesi verir |
| `sample_rate` | 48000, 24000, 16000, 8000 |
| `stream` | `true` ise ses üretildikçe gönderilir |

Yanıt bir WAV dosyasıdır (16 bit, mono); kullanılan seed `X-Seed` başlığında döner. `stream=true` ile yanıt başlıksız ham PCM'dir (16 bit, little-endian, mono), örnekleme hızı `X-Sample-Rate` başlığındadır ve gövde bağlantı kapanınca biter. Geçersiz istekler `400` ve `{"error": "..."}` döndürür; hata iletileri Türkçedir.

```bash
curl "localhost:8000/tts?text=Merhaba" -o merhaba.wav
curl localhost:8000/tts -d '{"text": "Siparişiniz yola çıktı.", "speed": 1.2}' -o siparis.wav
curl -X POST --data-binary @kitap.epub "localhost:8000/api/books?name=kitap.epub"
```

## Komut satırı

`ema.py`, okuyucu olmadan metni doğrudan uçbirimden seslendirir.

```bash
uv run ema.py "Merhaba dünya"              # hoparlörden çal
uv run ema.py "Merhaba" -o merhaba.wav     # dosyaya yaz
uv run ema.py -f metin.txt -o sesler       # her satır için bir ses: sesler/0.wav, 1.wav, ...
echo "Merhaba" | uv run ema.py             # stdin'den oku
uv run ema.py                              # etkileşimli kip: yaz, Enter'a bas, dinle
```

Hoparlörden çalmak için sistemde PortAudio kurulu olmalıdır.

| Seçenek | Açıklama | Varsayılan |
|---|---|---|
| `-f DOSYA` | Metin dosyası; her satır ayrı seslendirilir | |
| `-o YOL` | Çalmak yerine yaz: tek metin için bir `.wav`, birden çok satır için bir klasör | |
| `--speed` | Konuşma hızı, 0.25 ile 4 arası; 1'in altı daha yavaş | `$EMA_SPEED`, yoksa 1.0 |
| `--seed` | Aynı seed aynı sesi verir | rastgele |
| `--rate` | Örnekleme hızı: 48000, 24000, 16000, 8000 | 48000 |
| `--api URL` | Modeli yüklemek yerine çalışan bir `app.py` kullan | `$EMA_API` |
| `--cpu` | GPU yerine CPU kullan | |
| `--lightning` | NVIDIA hızlı yolu; açılışta derlenir, bu dakikalar sürer | |

Etkileşimli kipte `/speed 0.8` sonraki metinlerin hızını değiştirir, `Ctrl+C` çalan sesi durdurur, `Ctrl+D` çıkar.

Her çağrı modeli baştan yükler; bu yaklaşık 3 saniye sürer. `app.py` çalışırken `--api http://127.0.0.1:8000` (ya da `export EMA_API=...`) bunu atlar ve yaklaşık 0,2 saniyede yanıt verir.

## Hız

RTX 4050 ve 16 çekirdekli işlemcisi olan bir dizüstü bilgisayarda ölçüldü:

| | Süre |
|---|---|
| Isınmış modelde tek cümle, GPU | yaklaşık 20 ms |
| 5 saniyelik bir cümle, CPU | yaklaşık 0,3 sn |
| 34 dakikalık bir bölümün MP3'e aktarılması, GPU | 25 sn |
| Masaüstü penceresinin kullanıma hazır olması | yaklaşık 2 sn |
