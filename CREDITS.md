# Credits

This plugin is for educational videos with talking-head footage. It
passes on work by other people. Thank you to each of them.

## Skills and code passed on

- **perfect-cuts** and **perfect-clips**: Vic Laranja, Systems by Vic.
  YouTube: [youtube.com/@systemsbyvic](https://www.youtube.com/@systemsbyvic).
  Web: [systemsbyvic.com](https://systemsbyvic.com).
  MIT License, Copyright (c) 2026 Systems by Vic. The full license ships
  in each skill's folder. The copies here use Parakeet for transcription,
  and perfect-cuts adds a Final Cut exporter.
- **stop-slop writing rules**, adapted inside perfect-clips: Hardik Pandya.
  Web: [hvpandya.com](https://hvpandya.com).
  Code: [github.com/hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop).
  MIT License, Copyright (c) 2025 Hardik Pandya. The notice ships in
  `perfect-clips/THIRD-PARTY-NOTICES.md`.

## Methods and ideas

- **first-impression** follows the "Holy Trifecta" method of Shane Hummus:
  the title, the thumbnail and the opening make one promise.
  YouTube: [youtube.com/@ShaneHummus](https://www.youtube.com/@ShaneHummus).
  The skill is written new for this plugin; his wording is not copied.

## Fonts and models

- **Inter**, the default font for text cards: Rasmus Andersson.
  [SIL Open Font License 1.1](https://openfontlicense.org); the license
  text ships beside the font file.
- **Montserrat**, inside perfect-clips: The Montserrat Project Authors.
  [SIL Open Font License 1.1](https://openfontlicense.org); `OFL.txt`
  ships beside the font file.
- **Parakeet TDT 0.6b v3** (NVIDIA), the transcription model. Setup
  downloads it; the plugin does not ship it.
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), per its
  [model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3).
- **YuNet face detection** ([OpenCV Zoo](https://github.com/opencv/opencv_zoo)),
  used by perfect-clips to find the speaker in the frame. Downloaded at
  first use; not shipped. Apache License 2.0.

## Tools the plugin installs, under their own licenses

- **Remotion**, which draws the text cards. Remotion is not MIT. It is
  free for individuals, for-profit companies with up to 3 employees, and
  non-profit organizations, universities included. A larger for-profit
  company needs a Remotion company license. Terms:
  [remotion.dev/license](https://www.remotion.dev/license).
- **parakeet-mlx** (senstella), which runs Parakeet on Apple Silicon:
  Apache License 2.0. [github.com/senstella/parakeet-mlx](https://github.com/senstella/parakeet-mlx)
- **DeepFilterNet** (Hendrik Schröter), which removes background noise:
  MIT or Apache License 2.0, at your option.
  [github.com/Rikorose/DeepFilterNet](https://github.com/Rikorose/DeepFilterNet)
- **pypdfium2**, which reads slide decks saved as PDF: Apache License 2.0
  or BSD-3-Clause. It bundles **PDFium** (BSD-3-Clause).
  [github.com/pypdfium2-team/pypdfium2](https://github.com/pypdfium2-team/pypdfium2)
- **ffmpeg**, installed through Homebrew, under its own license (LGPL or
  GPL, depending on the build). [ffmpeg.org/legal.html](https://ffmpeg.org/legal.html)
