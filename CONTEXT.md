# Раскраска: domain terms

The names the code and its reviews use for the parts of the game.

- **Picture** (картина, раскраска): a painting or photo split into numbered
  regions, kept as a `.svgz` (see CLAUDE.md for the format); its id names
  where it came from: `builtin-`, `photo-`, `wd-`.
- **Level**: the size of regions, 2/3/4/5 (about 120/300/600/1000
  regions); in the gallery also 8 (downloaded) and 9 (own photo).
- **Grade** (размер областей): a level as the preview offers it: Крупные,
  Мелкие, Очень мелкие.
- **Преобразование** (Conversion): making an image into a picture with
  `pbn.py`; `haltia_paint/convert.py` is the one queue of it.
  - **Urgent work**: what the person is waiting for (a grade in the
    preview); it goes first and stops background work.
  - **Background work**: photos of `Изображения/Раскраски`; stopped by
    urgent work and started again after it.
  - **Job**: one image to one picture; it can be cancelled (leaving the
    preview cancels its grades).
- **Preview** (Картина): a found painting or own picture shown as each
  grade will paint it, before it is taken into the gallery.
- **Progress** (прогресс): which regions of a picture are painted, in
  `progress/<id>.json`; not the progress of a conversion, which is a
  share shown as a bar.
