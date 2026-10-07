# Geliştirme

EMA Reader'ın teknik tarafı: nasıl kurulduğu, kaynaktan nasıl çalıştırıldığı, HTTP API'si, komut satırı aracı ve kurulum dosyalarının nasıl üretildiği.

## Düzen

| Dosya | Ne yapar |
|---|---|
| `app.py` | Sunucu: kitaplık, seslendirme, dışa aktarım ve sayfanın kendisi |
| `extract.py` | EPUB, PDF, metin, Markdown ve web sayfalarını kapak ve ayrıntılarıyla birlikte cümlelerden oluşan bölümlere çevirir |
| `export.py` | Bir bölümü ya da kitabı MP3, OGG, Opus, FLAC, WAV veya metin olarak yazar |
| `ema.py` | Modeli yükler; ayrıca metni seslendiren bir komut satırı aracıdır |
| `update.py` | GitHub'daki son sürüme bakar; yeni sürüm varsa uygulama bunu haber verir |
| `desktop.py` | Sunucunun çevresindeki masaüstü penceresi |
| `build.py` | Windows ve macOS için kendi kendine yeten uygulamayı üretir |
| `packaging/linux.py` | Linux için `.deb` ve `.rpm` paketlerini üretir |
| `packaging/arch/PKGBUILD` | AUR'daki Arch Linux paketi |
| `static/index.html` | Arayüzün tamamı: tek sayfa, derleme adımı yok |
| `CHANGELOG.md` | Her sürümün yenilikleri; sürüm sayfasına ve uygulamadaki "Yeni sürüm" penceresine buradan yazılır |
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

Linux'ta masaüstü, bir pencerenin simgesini uygulama kimliğiyle aynı adı taşıyan başlatıcı dosyasından bulur. `--install` yapılmamışsa uygulama ilk açılışta menüde görünmeyen bir başlatıcı (`NoDisplay=true`) ve simgeyi kendisi yazar; yoksa pencere masaüstünün yer tutucu simgesiyle görünürdü. Paketten kurulan kopya bunu yapmaz: başlatıcıyı paket getirir ve kullanıcının klasöründeki aynı adlı bir başlatıcı onu menüden gizlerdi.

## Kurulum dosyalarını üretme

```bash
uv run build.py        # Windows ya da macOS'te; dist/EMA Reader/ klasörünü yazar
```

Çıktı; içinde Python, yalnızca CPU'lu bir PyTorch ve model ağırlıkları bulunan bir PyInstaller klasörüdür, bu yüzden uygulama indirme yapmadan açılır. PyTorch'un GPU'lu sürümü birkaç gigabayt eklerdi; model CPU'da da yeterince hızlıdır.

`.github/workflows/build.yml`, `v1.0.0` gibi bir sürüm etiketi gönderildiğinde derlemeyi Windows ve macOS'te çalıştırır (Linux paketleri için aşağıya bak), bir kurulum dosyasına (`EMA-Reader-Setup.exe`, `packaging/windows.iss` ile üretilir) ve bir disk görüntüsüne (`EMA-Reader.dmg`) sarar, ikisini de sürüme ekler. Actions sekmesinden elle de başlatılabilir.

Kurulum dosyaları kod imzalı değildir; bu yüzden Windows SmartScreen ve macOS Gatekeeper ilk açılıştan önce uyarır.

### Linux paketleri

```bash
sudo python3 packaging/linux.py ubuntu-24.04     # o sistemin kendisinde; dist/EMA-Reader-ubuntu-24.04.deb yazar
```

Linux penceresi GTK 4, libadwaita ve WebKitGTK'yı sistemden aldığı için, Windows ve macOS'teki gibi her şeyi içeren tek bir klasör olamaz. Paket bunun yerine uygulamayı `/opt/ema-reader` altına, sistemin kendi Python'uyla kurulmuş bir ortamla birlikte koyar. Bu ortamda yalnızca CPU'lu bir PyTorch, model ağırlıkları ve öbür paketler bulunur; GTK'nın Python bağları (`python3-gi` ya da `python3-gobject`) sistemden gelir. Ortam yalnızca kurulduğu Python sürümüyle çalıştığı için her sistemin kendi paketi vardır ve paket tam o Python sürümünü ister. Betik `dpkg-deb` bulursa `.deb`, `rpmbuild` bulursa `.rpm` üretir. Root olarak çalışır, çünkü ortamı kurulacağı yerde, `/opt/ema-reader` içinde hazırlar.

Paket ayrıca `/usr/bin/ema-reader` komutunu, uygulamalar menüsündeki başlatıcıyı, simgeyi ve yazılım merkezleri için bir AppStream açıklamasını kurar.

`build.yml` her sürümde Ubuntu 24.04, Ubuntu 26.04, Debian 13 ve Fedora 44 için birer paket üretir. Her biri o sistemin kabında derlenir, sonra kurulup sıradan bir kullanıcıyla `ema-reader --check` ile denenir. Yeni bir sistem eklemek için iş akışındaki listeye bir satır eklemek yeterlidir; adı `EMA-Reader-<sistem>.deb` ya da `.rpm` olur.

### Arch Linux

Arch'a hazır paket verilmez: Arch sürekli güncellendiği için ortamın kurulduğu Python sürümü kısa sürede eskir. Onun yerine AUR'da bir `PKGBUILD` durur (`packaging/arch/PKGBUILD`) ve paket okuyucunun kendi bilgisayarında `makepkg` ile derlenir. Ortam aynı biçimde `/opt/ema-reader` altına kurulur, ama PyTorch'u Arch'ın kendi `python-pytorch` paketinden alır; onun yerine `python-pytorch-cuda` kuruluysa NVIDIA kartı kullanılır. PyPI'dan yalnızca Arch'ın paketlemediği şeyler gelir. Uygulamanın kendi dosyalarını ve başlatıcısını `packaging/linux.py --layout` yazar, böylece öbür paketlerle aynı kalırlar.

Bu kopya kendini güncellemez; güncellemeyi okuyucunun AUR yardımcısı yapar. Uygulama yeni sürümü haber verir, "Güncelle"ye basılırsa bunu söyler.

`build.yml` her çalışmada paketi bir Arch kabında `makepkg -si` ile derler, kurar ve `ema-reader --check` ile dener. Sürüm etiketinde, GitHub'ın o sürüm için verdiği kaynağın sağlama toplamını `PKGBUILD`'e yazar ve dosyayı sürüme ekler. AUR'a yayınlamak için o dosyayı AUR'daki `ema-reader` deposuna koy, `makepkg --printsrcinfo > .SRCINFO` çalıştır, ikisini gönder:

```bash
git clone ssh://aur@aur.archlinux.org/ema-reader.git && cd ema-reader
cp ~/İndirilenler/PKGBUILD . && makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO && git commit -m "1.1.0" && git push
```

## Sürüm yayınlama

1. `app.py` içindeki `VERSION`, `pyproject.toml` içindeki `version` ve `packaging/arch/PKGBUILD` içindeki `pkgver` değerini yükselt (üçü aynı olmalı).
2. `CHANGELOG.md` dosyasının başına `## 1.1.0` gibi bir bölüm ekle ve yenilikleri kullanıcının anlayacağı dille yaz.
3. Değişiklikleri gönder, sonra sürümü etiketle:

```bash
git tag v1.1.0
git push origin v1.1.0
```

Etiket gelince `build.yml` kurulum dosyalarını üretir ve `CHANGELOG.md` içindeki o bölümü not olarak koyduğu bir GitHub sürümü açar. Arch için sürüme eklenen `PKGBUILD`'i ayrıca AUR'a gönder (yukarıya bak). Etiket, `VERSION` ve `CHANGELOG.md` birbirini tutmuyorsa derleme durur; aynı şeyi testler de denetler.

Uygulama açılışta `update.py` aracılığıyla GitHub'daki son sürüme bakar (yanıt altı saat saklanır; Ayarlar'daki "Denetle" hemen yeniden sorar). Kendi sürümünden yenisini bulursa kitaplığın üstünde "EMA Reader 1.1.0 yayınlandı" çubuğunu gösterir; aynı bilgi Ayarlar'daki sürüm satırında da durur. Açılıştaki denetim Ayarlar'dan kapatılabilir. Ön sürümler ve taslaklar haber verilmez.

"Güncelle" o sürümün notlarını gösterir ve kurulumu uygulamanın içinden yapar; kullanıcının bir şey indirmesi ya da komut yazması gerekmez:

- **Kaynaktan çalışan kopya (Linux):** `git pull --ff-only` ile yeni kodu alır, Python ortamı projenin kendi `.venv` klasörüyse `uv sync` ile paketleri eşitler, sonra kendini yeniden başlatır.
- **Windows:** yeni kurulum dosyasını indirir, sessizce çalıştırır ve kapanır; kurulum bitince uygulamayı yeniden açar.
- **macOS:** yeni disk görüntüsünü indirir, uygulama kapanınca içindeki uygulamayı eskisinin yerine koyar ve yeniden açar. Eski uygulama, yenisi tümüyle kopyalanana kadar silinmez.
- **Linux paketi:** aynı sistemin yeni paketini indirir (hangisi olduğunu paketin `/opt/ema-reader/package` dosyasına yazdığı addan bilir), `pkexec` ile `apt-get` ya da `dnf`'e kurdurur, sonra kendini yeniden başlatır. Sistem kullanıcının parolasını kendi penceresinde sorar. O sistem için paket yayınlanmamışsa uygulama güncellemeyi sunar ama kurulum dosyası olmadığını söyler.
- **Arch Linux:** kendini güncellemez; güncellemeyi AUR yardımcısı yapar. "Güncelle" bunu söyler.

Güncellemeyi yalnızca aynı bilgisayardan gelen ve uygulamanın kendi sayfasının gönderdiği istek başlatabilir (`POST /api/update`, `X-EMA-Reader: update` başlığıyla). Kurulum dosyaları yalnızca `https://github.com/` adresinden indirilir.

Yayınlamadan denemek için `EMA_READER_UPDATE_URL` ile GitHub'ın sürüm yanıtı biçiminde bir dosya gösterilebilir:

```bash
echo '{"tag_name": "v9.0.0", "body": "- Deneme"}' > /tmp/surum.json
EMA_READER_UPDATE_URL=file:///tmp/surum.json uv run app.py
```

## Testler

```bash
uv run --with pytest pytest
```

Testler metin çıkarmayı, dışa aktarım adlandırmasını ve güncelleme denetimini kapsar, modeli yüklemez. `.github/workflows/test.yml` onları her gönderimde çalıştırır.

## HTTP API

| Uç nokta | Açıklama |
|---|---|
| `GET /api/books` | Kitaplık |
| `POST /api/books?name=kitap.epub` | Dosya ekle; isteğin gövdesi dosyanın kendisidir |
| `POST /api/books` | Makale ekle: `{"url": "https://..."}` |
| `POST /api/books?preview=1…` | Eklemeden oku: bulunanı (başlık, bölüm sayısı, ilk cümleler) ve bir `token` döndürür; makalede `"preview": true` |
| `POST /api/pending/TOKEN` | Önizlenen şeyi kitaplığa ekle |
| `DELETE /api/pending/TOKEN` | Önizlemeyi unut |
| `GET /api/pending/TOKEN/cover` | Önizlenen şeyin kapağı, varsa |
| `GET /api/books/ID` | Metni ve ayrıntılarıyla tek bir kitap |
| `DELETE /api/books/ID` | Kitabı kaldır |
| `PUT /api/books/ID/progress` | `{"chapter": 0, "sentence": 12}` |
| `GET /api/books/ID/cover` | Kitabın kapağı varsa kapak resmi |
| `POST /api/books/ID/export` | Dışa aktarımı başlat; `{"job": "..."}` döner |
| `GET /api/exports/JOB` | `{"state": "working", "progress": 0.4, "name": "..."}` |
| `GET /api/exports/JOB/file` | Hazır dosya |
| `DELETE /api/exports/JOB` | Dışa aktarımı iptal et |
| `GET /api/update` | `{"current": "1.0.0", "latest": "1.1.0", "newer": true, "notes": "...", "page": "...", "download": "...", "job": {...}}`; `?fresh=1` yeniden sorar |
| `POST /api/update` | Yeni sürümü kurar ve uygulamayı yeniden başlatır; yalnızca bu bilgisayardan |
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
