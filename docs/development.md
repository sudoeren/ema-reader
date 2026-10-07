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
| `build.py` | Windows ve macOS için uygulamayı üretir |
| `runtime.py` | İlk açılışta bilgisayara uyan PyTorch'u ve modeli indirir |
| `packaging/linux.py` | Linux için `.deb`, `.rpm` ve pacman paketlerini, öbür dağıtımlar için de `.tar.gz` klasörünü üretir |
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
uv run --extra desktop desktop.py --check        # penceresiz başlat, gerekeni indir, bir cümle üret, çık
```

Linux'ta masaüstü, bir pencerenin simgesini uygulama kimliğiyle aynı adı taşıyan başlatıcı dosyasından bulur. `--install` yapılmamışsa uygulama ilk açılışta menüde görünmeyen bir başlatıcı (`NoDisplay=true`) ve simgeyi kendisi yazar; yoksa pencere masaüstünün yer tutucu simgesiyle görünürdü. Paketten kurulan kopya bunu yapmaz: başlatıcıyı paket getirir ve kullanıcının klasöründeki aynı adlı bir başlatıcı onu menüden gizlerdi.

## İlk açılıştaki indirme

Kurulum dosyaları PyTorch'u ve modeli içermez. NVIDIA kartları için PyTorch tek başına bir GitHub sürüm dosyasının sınırı olan 2 GB'tan büyüktür, ayrıca her bilgisayar başka bir sürümünü ister. Bunun yerine `runtime.py` ilk açılışta bilgisayara uyanı indirir:

PyTorch kendi dizininden (`download.pytorch.org/whl/cpu`, `cu126`…) alınır, bağımlılıkları PyPI'dan. uv'ye PyTorch'un dizini `--extra-index-url` olarak verilir, çünkü uv önce ona bakar; tersi yapılırsa PyTorch PyPI'dan gelir, o da Linux'ta NVIDIA kartları için olan 5 GB'lık, Windows'ta ise yalnızca işlemciyi kullanan derlemedir.

| Seçenek | Ne zaman sunulur | PyTorch nereden gelir |
|---|---|---|
| NVIDIA ekran kartı (`cuda`) | Windows ve Linux'ta NVIDIA sürücüsü kuruluysa (`nvidia-smi`, `nvcuda.dll` ya da `/proc/driver/nvidia`) | `download.pytorch.org/whl/cu126`, olmazsa `cu128`, `cu130` |
| Apple silicon (`mps`) | Apple silicon'lu Mac'te, tek seçenek olarak | PyPI; macOS sürümü ekran kartını da kullanır |
| İşlemci (`cpu`) | Windows ve Linux'ta her zaman | `download.pytorch.org/whl/cpu` |

Sayfa sunucu açılır açılmaz gelir; model yoksa `/api/setup` hazır olmadığını söyler ve sayfa kütüphane yerine indirme ekranını gösterir. Seçilen PyTorch, uygulamayla gelen `uv` ile kullanıcının veri klasörüne (`.../EMA Reader/runtime/site`) kurulur ve `desktop.py` onu `sys.path`'in başına ekler. Model de masaüstü uygulamasında aynı klasöre (`runtime/hf`) iner. Bitince model yüklenir ve sayfa kütüphaneye geçer.

Ayarlar'daki "Seslendirme" işlemci ile ekran kartı arasında geçiş yapar. İşlemciye geçmek için bir şey indirilmez: ekran kartı için inen PyTorch (ve kaynaktan çalışan kopyanın kendi PyTorch'u) işlemcide de çalışır. Seçim `runtime/state.json` içine `use` olarak yazılır ve model yeniden başlatmadan, seçilenin üzerinde yeniden yüklenir; o ana kadar eski model okumayı sürdürür. Yalnızca işlemci için inmiş PyTorch'tan ekran kartına geçerken yeni bir indirme gerekir: çalışan uygulama yüklediği PyTorch'u bırakamayacağı için yenisi `runtime/site.new`'e iner ve uygulama yeniden başlayınca eskisinin yerini alır.

Ayarlar'daki "İndirilenler" bunların hepsini kaldırır (`runtime/site`, `site.new`, `cache`, `hf`; kaynaktan çalışan kopyada modelin ortak Hugging Face önbelleğindeki klasörü). Dosyalar uygulama çalışırken kullanımda olduğu için o anda silinmez: `runtime/remove` adında bir işaret yazılır, uygulama yeniden başlar ve yeni açılan uygulama her şeyden önce onları siler. Bu, paket kaldırıldığında kullanıcının klasöründe kalan gigabaytları geri almanın yoludur; Windows kaldırıcısı aynı klasörü kendisi de siler.

Model hangi cihazda çalışacağını `ema.best_device()` ile seçer: NVIDIA kartı, yoksa Apple silicon'un ekran kartı (MPS), yoksa işlemci. EMA Lightning'in kendi "auto" seçimi yalnızca NVIDIA'yı tanıdığı için uygulama cihazı kendisi verir. MPS'te olmayan işlemler işlemciye düşer (`PYTORCH_ENABLE_MPS_FALLBACK`); model MPS'te hiç çalışmazsa işlemciyle yüklenir.

## Kurulum dosyalarını üretme

Üç sistemde de uygulama kendi Python'unu taşır: `uv` ile indirilen python-build-standalone, içine uygulamanın açılmak için gerektirdiği paketler (PyTorch'suz) ve ilk açılıştaki indirme için `uv`'nin kendisi. Uygulamanın Python'u sistemdekinden bağımsızdır.

```bash
uv run --no-project build.py         # Windows'ta dist/EMA Reader/, macOS'te dist/EMA Reader.app
sudo python3 packaging/linux.py      # Linux'ta (Ubuntu 24.04); dist/EMA-Reader.deb, .rpm ve .pkg.tar.zst
```

- **Windows:** `dist/EMA Reader/python/` Python'dur; içindeki `EMA Reader.exe`, pencereli çalışan `pythonw.exe`'nin uygulamanın adı ve simgesiyle (rcedit varsa) bir kopyasıdır ve kısayollar onu `desktop.py` ile başlatır. `packaging/windows.iss` bunu kullanıcı başına kurulan bir kurulum dosyasına sarar. Kaldırınca indirilen PyTorch ve model de silinir, kitaplık ve ayarlar kalır.
- **macOS:** Python `.app` paketinin `Contents` klasörüdür; `Contents/MacOS/python` onun bir kopyasıdır ve paketin ana programı olan küçük bir betik onu `desktop.py` ile başlatır. Python paketin içinden çalıştığı için Dock'ta uygulamanın adı ve simgesi görünür.
- **Linux:** Uygulama `/opt/ema-reader` altına gider. GTK'nın Python bağları (PyGObject) uygulamanın Python'u için derlenir ve sistemin GTK 4, libadwaita, WebKitGTK, GLib ve cairo kitaplıklarını kullanır; bunların arayüzleri sabit olduğu için aynı derleme Ubuntu, Debian, Fedora ve Arch'ta çalışır. Derleme desteklenen en eski sistem olan Ubuntu 24.04'te yapılır, böylece yenilerinde de çalışır; `gcc`, `pkg-config`, `libgirepository-2.0-dev`, `libcairo2-dev`, `rpm` ve `libarchive-tools` gerekir. Aynı uygulama üç pakete sarılır; pacman paketi `makepkg` kullanılmadan, makepkg'nin de yazdığı `.PKGINFO` ve `.MTREE` açıklamalarıyla `bsdtar` ile yazılır. Paketler ayrıca `/usr/bin/ema-reader` komutunu, uygulamalar menüsündeki başlatıcıyı, simgeyi ve yazılım merkezleri için bir AppStream açıklamasını kurar.
- **Linux, öbür dağıtımlar:** `EMA-Reader.tar.gz` tek bir `ema-reader/` klasörüdür ve Windows ile macOS derlemeleri gibi kurulur: paketler bir sanal ortama değil Python'un kendisine konur, bu yüzden klasör her yerde durabilir ve kök yetkisi istemez. İçindeki `install` pencerenin sistemden istediklerini (GTK 4, libadwaita, WebKitGTK 6.0) yoklar ve uygulamayı menüye ekler; `uninstall` menüden çıkarıp klasörü siler. Yalnızca bunu üretmek için: `python3 packaging/linux.py tar.gz` (kök yetkisi gerekmez).

Her derleme, paketin adını uygulamanın `package` dosyasına yazar; `update.py` güncellemeyi buna bakarak yapar.

`.github/workflows/build.yml` bir sürüm etiketi gönderildiğinde (ya da Actions sekmesinden elle) hepsini üretir ve dener:

- Windows ve macOS derlemesi `desktop.py --check` ile açılır: ilk açılıştaki gibi PyTorch'u ve modeli indirir ve bir cümle seslendirir. Windows'ta NVIDIA'lı PyTorch da ayrıca indirilip yüklenir; makinede kart olmadığı için işlemcide çalışır, ama indirmenin ve paket deposunun doğru olduğu görülür. Pencere açılmaz, ama pencerenin kitaplıkları (pywebview; Windows'ta pythonnet, macOS'te AppKit ve WebKit) yüklenir.
- Linux paketleri Ubuntu 24.04 ve 26.04, Debian 13, Fedora 44 ve Arch kaplarına okuyucunun kuracağı gibi kurulur ve sıradan bir kullanıcıyla `ema-reader --check` çalıştırılır. Ubuntu 24.04'te NVIDIA'lı PyTorch da denenir. `.tar.gz` klasörü openSUSE Tumbleweed kabında bir kullanıcının ev klasörüne açılıp aynı biçimde denenir. Denetim, inen PyTorch'un istenen türde olduğuna da bakar (işlemci istenince `+cpu`, NVIDIA istenince `+cu…`).

GitHub'ın makinelerinde ekran kartı olmadığından ekran kartıyla çalışmayı bu denemeler göstermez; onu gerçek bir NVIDIA'lı bilgisayarda ve bir Apple silicon Mac'te denemek gerekir.

Kurulum dosyaları kod imzalı değildir; bu yüzden Windows SmartScreen ve macOS Gatekeeper ilk açılıştan önce uyarır.

Windows kurulum dosyası, pencereyi çizen WebView2 bilgisayarda yoksa (bazı Windows 10'larda) Microsoft'un küçük kurucusunu çalıştırır; `build.yml` onu derleme sırasında indirir. macOS disk görüntüsünde uygulamanın yanında Uygulamalar klasörüne bir bağlantı durur.

## Sürüm yayınlama

1. `app.py` içindeki `VERSION` ile `pyproject.toml` içindeki `version` değerini yükselt (ikisi aynı olmalı).
2. `CHANGELOG.md` dosyasının başına `## 1.1.0` gibi bir bölüm ekle ve yenilikleri kullanıcının anlayacağı dille yaz.
3. Değişiklikleri gönder, sonra sürümü etiketle:

```bash
git tag v1.1.0
git push origin v1.1.0
```

Etiket gelince `build.yml` kurulum dosyalarını üretir ve `CHANGELOG.md` içindeki o bölümü not olarak koyduğu bir GitHub sürümü açar. Etiket, `VERSION` ve `CHANGELOG.md` birbirini tutmuyorsa derleme durur; aynı şeyi testler de denetler.

Uygulama açılışta `update.py` aracılığıyla GitHub'daki son sürüme bakar (yanıt altı saat saklanır; Ayarlar'daki "Denetle" hemen yeniden sorar). Kendi sürümünden yenisini bulursa kitaplığın üstünde "EMA Reader 1.1.0 yayınlandı" çubuğunu gösterir; aynı bilgi Ayarlar'daki sürüm satırında da durur. Açılıştaki denetim Ayarlar'dan kapatılabilir. Ön sürümler ve taslaklar haber verilmez.

"Güncelle" o sürümün notlarını gösterir ve kurulumu uygulamanın içinden yapar; kullanıcının bir şey indirmesi ya da komut yazması gerekmez:

- **Kaynaktan çalışan kopya (Linux):** `git pull --ff-only` ile yeni kodu alır, Python ortamı projenin kendi `.venv` klasörüyse `uv sync` ile paketleri eşitler, sonra kendini yeniden başlatır.
- **Windows:** yeni kurulum dosyasını indirir, sessizce çalıştırır ve kapanır; kurulum bitince uygulamayı yeniden açar.
- **macOS:** yeni disk görüntüsünü indirir, uygulama kapanınca içindeki uygulamayı eskisinin yerine koyar ve yeniden açar. Eski uygulama, yenisi tümüyle kopyalanana kadar silinmez.
- **Linux paketi:** aynı sistemin yeni paketini indirir (hangisi olduğunu paketin `/opt/ema-reader/package` dosyasına yazdığı addan bilir), `pkexec` ile `apt-get`, `dnf` ya da `pacman`'a kurdurur, sonra kendini yeniden başlatır. Sistem kullanıcının parolasını kendi penceresinde sorar. O sistem için paket yayınlanmamışsa uygulama güncellemeyi sunar ama kurulum dosyası olmadığını söyler.
- **Linux klasörü (`.tar.gz`):** yenisini indirir, klasörün yanına açar, eskisiyle yer değiştirir ve kendini yeniden başlatır; parola gerekmez. Eski klasör, yenisi yerine oturana kadar silinmez.

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
| `GET /api/downloads` | `{"bytes": 123}`: ilk açılışta indirilen PyTorch ve modelin diskte tuttuğu yer |
| `DELETE /api/downloads` | Onları kaldırır ve uygulamayı yeniden başlatır; yalnızca bu bilgisayardan |
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
