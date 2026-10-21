# Раскраска: domain terms

The names the code and its reviews use for the parts of the game.

- **Picture** (картина, раскраска): a painting or photo split into numbered
  regions, kept as a `.svgz` (see AGENTS.md for the format); its id names
  where it came from: `builtin-`, `photo-`, `wd-`.
- **Level**: the size of regions, 2/3/4/5 (about 120/300/600/1000
  regions); in the gallery also 8 (downloaded) and 9 (own photo).
- **Grade** (размер областей): a level as the preview offers it: Крупные,
  Средние (where the preview starts), Мелкие.
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
- **Section** (раздел): a heading of the gallery and its cards,
  `haltia_paint/sections.py`: Продолжить (begun), then the themes or the
  difficulties, then Готовые (finished).
  - **Theme** (тема): what a picture shows: Природа, Море и корабли,
    Животные, Цветы, Японская гравюра, Дома и города, Люди, Натюрморт,
    Разное, and Мои фотографии for own pictures.
  - **Difficulty** (сложность): Лёгкие, Средние, Сложные, Очень
    сложные, by the count of regions.
- **Hint** (подсказка «где?»): the button that shows the nearest
  region of the chosen colour still to paint; may be hidden, limited
  per picture (the count kept in its Progress) and zoom more or less.
  The **rings** round the last regions of a colour are a hint too.
- **Отклик** (Feedback): the sound and the buzz when a colour or a
  picture is done, `haltia_paint/feedback.py`.
- **End** (конец картины): the replay (повтор: the picture painted again
  in the order it was painted) and «Готово!» with its buttons;
  **Оригинал** is the painting the picture was made from.

## Words on the screen

Since 4.5 the screen says one thing one way:

- what is painted is a **картина** (not картинка; картинка is an image
  file one picks, a photo or a drawing);
- **Галерея** is only the photos program (Взять из Галереи, Сохранить в
  Галерею); the program's own list of pictures is **Раскраски**;
- taking a picture in is **Добавить** (the preview's button,
  **Раскрашивать**, adds it and opens it); a downloaded one is taken out
  with **Убрать**; progress is wiped with **Начать заново**.
