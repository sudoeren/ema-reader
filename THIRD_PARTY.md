# Third-party work

EMA Reader's own code is under the MIT License (see `LICENSE`). It builds on the following, each under its own licence.

| What | Used for | Licence |
|---|---|---|
| [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) by Canberk Aslan (model weights and the `ema-lightning` package) | The voice | Apache 2.0 |
| [normalizer-tr](https://github.com/erdemtuna/normalizer-tr) by Erdem Tuna | Reading numbers, dates and symbols | Apache 2.0 |
| [PyTorch](https://pytorch.org) | Running the model | BSD-3-Clause |
| [NumPy](https://numpy.org) | Audio arrays | BSD-3-Clause |
| [python-soundfile](https://github.com/bastibe/python-soundfile) and libsndfile | Writing MP3, OGG, Opus, FLAC and WAV | BSD-3-Clause, LGPL-2.1 |
| [sounddevice](https://python-sounddevice.readthedocs.io) and PortAudio | Playing audio from the command line | MIT |
| [pypdf](https://github.com/py-pdf/pypdf) | Reading PDF files | BSD-3-Clause |
| [trafilatura](https://github.com/adbar/trafilatura) | Reading articles from web pages | Apache 2.0 |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | Downloading the model | Apache 2.0 |
| [pywebview](https://pywebview.flowrl.com) | The window on Windows and macOS | BSD-3-Clause |
| [PyGObject](https://pygobject.gnome.org), GTK, libadwaita and WebKitGTK | The window on Linux (used from the system, not shipped) | LGPL-2.1 or later |
| [Inter](https://rsms.me/inter/), [Newsreader](https://github.com/productiontype/Newsreader) and [Caveat](https://github.com/googlefonts/caveat) | The app's fonts | SIL Open Font License 1.1 (texts in `static/fonts/`) |

The installers for Windows and macOS contain copies of the Python packages above and of the model weights.
