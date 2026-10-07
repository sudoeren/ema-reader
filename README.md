<p align="center"><img src="static/logo.svg" width="110" alt=""></p>

<h1 align="center">EMA Reader</h1>

<p align="center"><b>Kitaplarını ve makalelerini Türkçe dinle.</b><br>
Bir kitap ekle, oynat düğmesine bas; EMA Reader onu sana kendi bilgisayarında okusun.</p>

![Kitaplık](docs/screenshots/library.png)

## Neler yapar

- **Kitaplarını sesli okur.** Bir EPUB ya da PDF ekle veya bir makalenin adresini yapıştır, sonra dinle.
- **Nerede olduğunu gösterir.** Okunan cümle işaretlenir. Başka bir cümleye tıklarsan oradan devam eder.
- **Kaldığın yeri hatırlar.** Uygulamayı kapatıp yarın açtığında aynı cümleden devam eder.
- **Senin hızında okur.** İstediğin zaman yavaşlat ya da hızlandır.
- **Yanında götürmeni sağlar.** Bir bölümü ya da kitabın tamamını telefonun veya araban için MP3 olarak kaydet.
- **Gizli kalır.** Her şey kendi bilgisayarında olur. Hesap yok, abonelik yok; okudukların hiçbir yere gönderilmez.

![Bir kitabı dinlerken](docs/screenshots/reader.png)

## EMA Reader'ı edin

**Windows ve macOS:** kurulum dosyasını [Sürümler](../../releases) sayfasından indir ve aç.

Uygulama yeni ve ücretsiz olduğu için Windows ya da macOS ilk açılışta seni uyarabilir. Windows'ta "Ek bilgi"yi, ardından "Yine de çalıştır"ı seç; macOS'te uygulamaya sağ tıklayıp "Aç"ı seç.

**Linux:** [uv](https://docs.astral.sh/uv/) kur, sonra:

```bash
git clone https://github.com/sudoeren/ema-reader
cd ema-reader
uv run --extra desktop desktop.py --install
```

Bundan sonra EMA Reader uygulamalar menünde durur.

### En düşük sistem gereksinimleri

| | Windows | macOS | Linux |
|---|---|---|---|
| **Sistem** | Windows 10 ya da 11, 64 bit | Apple silicon'lu (M1 ve sonrası) bir Mac | 64 bit; GTK 4, libadwaita ve WebKitGTK 6.0 kurulu bir masaüstü |
| **Bellek** | 4 GB | 4 GB | 4 GB |
| **Boş disk alanı** | yaklaşık 2 GB | yaklaşık 2 GB | yaklaşık 6 GB |
| **Ekran kartı** | gerekmez | gerekmez | gerekmez; NVIDIA kart varsa kullanılır |

- Uygulama çalışırken yaklaşık 1 GB bellek kullanır.
- Ekran kartı olmadan da akıcı okur: bir cümlenin sesi, sıradan bir işlemcide cümlenin kendisinden çok daha kısa sürede hazırlanır.
- Dinlemek için internet gerekmez. İnternet yalnızca web'den makale eklerken, yeni sürüm denetiminde ve Linux'ta ilk kurulumda (ses modeli ve gerekli paketler indirilirken) kullanılır.
- Linux'taki disk ihtiyacının çoğu, ekran kartı desteğiyle birlikte gelen PyTorch paketleridir.

## İlk dakikan

EMA Reader'ı ilk açtığında sana etrafı gezdirir. Kısa bir karşılama metni hazır bekler; oynat düğmesine basıp hemen dinleyebilirsin. Tanıtım da sesli anlatılır; sonradan Ayarlar'dan yeniden izleyebilirsin.

![İlk açılıştaki tanıtım](docs/screenshots/tour.png)

## Nasıl kullanılır

**Dinleyecek bir şey ekle.** "Kitap ya da makale ekle"yi seç; sonra pencereye bir dosya bırak, bir dosya seç ya da bir web adresi yapıştır.

**Dinle.** Oynat düğmesine bas. Yanındaki iki okla bir cümle geri ya da ileri git, sağdaki sayıyla hızı değiştir.

**Kitabın ne anlattığına bak.** Her kitabın kapağını, tanıtımını ve içindekileri gösteren bir ayrıntı sayfası vardır.

![Bir kitabın ayrıntıları](docs/screenshots/details.png)

**Sonrası için kaydet.** Tek bir bölümü ya da kitabın tamamını indir. MP3 her yerde çalar; daha küçük dosya ya da daha yüksek kalite istersen öbür seçenekler de orada.

![İndirme seçenekleri](docs/screenshots/download.png)

**Kendine göre ayarla.** Ayarlar'da koyu temaya geçebilir, bir renk seçebilir ve yazıyı büyütebilirsin.

![Koyu tema](docs/screenshots/dark.png)

## Bilmekte fayda var

- EMA Reader'ın tek bir sesi vardır ve **yalnızca Türkçe** okur; uygulamanın kendisi de Türkçedir. Yabancı sözcükler Türkçeymiş gibi okunur.
- Yalnızca sayfa resimlerinden oluşan taranmış bir PDF'te okunacak metin yoktur.
- Ses yapay zekâ ile üretilir. Bir kaydı paylaşırsan bunu belirt.
- Sayılar, tarihler ve kısaltmalar kendiliğinden okunur; ara sıra yanlış çıkabilir.
- Yeni bir sürüm çıktığında uygulama açılışta haber verir. Bunun için yalnızca GitHub'a "son sürüm hangisi" diye sorar; istemezsen Ayarlar'dan kapatabilirsin.

## Emeği geçenler

Geliştiren: [Eren Çakar](https://erencakar.com).

Ses, Canberk Aslan'ın [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) modelidir. EMA Reader bağımsız bir projedir ve modelin yazarıyla bir bağı yoktur.

EMA Reader, [MIT Lisansı](LICENSE) altında açık kaynaklıdır. Üzerine kurulduğu çalışmalar [THIRD_PARTY.md](THIRD_PARTY.md) dosyasında listelenir. Ekran görüntülerindeki öyküler Ömer Seyfettin'e aittir ve kamu malıdır.

Geliştiriciysen: [docs/development.md](docs/development.md).
