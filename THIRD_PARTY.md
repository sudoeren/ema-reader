# Üçüncü taraf çalışmalar

EMA Reader'ın kendi kodu MIT Lisansı altındadır (bkz. `LICENSE`). Aşağıdaki çalışmaların üzerine kuruludur; her biri kendi lisansına tabidir.

| Ne | Ne için kullanılıyor | Lisans |
|---|---|---|
| Canberk Aslan'ın [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) modeli (model ağırlıkları ve `ema-lightning` paketi) | Ses | Apache 2.0 |
| Erdem Tuna'nın [normalizer-tr](https://github.com/erdemtuna/normalizer-tr) paketi | Sayıları, tarihleri ve simgeleri okumak | Apache 2.0 |
| [PyTorch](https://pytorch.org) | Modeli çalıştırmak | BSD-3-Clause |
| [NumPy](https://numpy.org) | Ses dizileri | BSD-3-Clause |
| [python-soundfile](https://github.com/bastibe/python-soundfile) ve libsndfile | MP3, OGG, Opus, FLAC ve WAV yazmak | BSD-3-Clause, LGPL-2.1 |
| [sounddevice](https://python-sounddevice.readthedocs.io) ve PortAudio | Komut satırından ses çalmak | MIT |
| [pypdf](https://github.com/py-pdf/pypdf) | PDF dosyalarını okumak | BSD-3-Clause |
| [trafilatura](https://github.com/adbar/trafilatura) | Web sayfalarından makale okumak | Apache 2.0 |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | Modeli indirmek | Apache 2.0 |
| [Python](https://www.python.org) ([python-build-standalone](https://github.com/astral-sh/python-build-standalone) derlemesi) | Kurulum dosyalarıyla gelen, uygulamaya özel Python | PSF-2.0 |
| [uv](https://github.com/astral-sh/uv) | İlk açılışta PyTorch'u indirmek | MIT ya da Apache 2.0 |
| Microsoft Edge WebView2 kurucusu | Windows'ta pencereyi çizen bileşeni, eksikse kurmak | Microsoft'un yazılım lisans koşulları |
| [pywebview](https://pywebview.flowrl.com) | Windows ve macOS'teki pencere | BSD-3-Clause |
| [PyGObject](https://pygobject.gnome.org), GTK, libadwaita ve WebKitGTK | Linux'taki pencere (PyGObject paketlerle birlikte gelir; GTK, libadwaita ve WebKitGTK sistemden kullanılır) | LGPL-2.1 ya da sonrası |
| [Inter](https://rsms.me/inter/), [Newsreader](https://github.com/productiontype/Newsreader) ve [Caveat](https://github.com/googlefonts/caveat) | Uygulamanın yazı tipleri | SIL Open Font License 1.1 (metinleri `static/fonts/` içinde) |

Windows ve macOS kurulum dosyaları, yukarıdaki Python paketlerinin ve model ağırlıklarının kopyalarını içerir.
