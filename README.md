# Раскраска

Раскраска по номерам на известных картинах (`haltia-paint`), сделанная для
пожилого человека: без таймера, очков и рекламы.

- Картина разбита на области с номерами, как в Happy Color и Daily Coloring;
  внизу палитра. Выбрал цвет, нажал на область — она
  закрашена. Нажатие чуть мимо маленькой области нужного номера тоже
  считается.
- Справа кнопки: приблизить, отдалить, вся картина, «где?» (ближайшая незакрашенная
  область выбранного цвета), отмена, «посмотреть» готовую картину.
- Прогресс сохраняется после каждого нажатия в `~/.local/share/haltia-paint/`
  (до версии 4.0 — `b8k-paint`, папка переносится при первом запуске).
- Готовую картину можно сохранить в галерею: `Изображения/Мои раскраски`.
- Обычная GTK-программа `io.github.haltia_de.Paint` (до версии 4.0 —
  `io.github.trudenboy.Paint`) для любого рабочего стола; на планшете
  оболочка Haltia даёт ей вибрацию касаний, шапку и диалоги своей темой GTK
  и закрывает её своим ✕, а вне оболочки у окна обычные кнопки рабочего
  стола, среди них «Закрыть».
- 37 встроенных картин в общественном достоянии (Айвазовский, Шишкин,
  Левитан, Куинджи, Хокусай, Ван Гог и другие), около 300 и около 600
  областей; `make-paintings.py` делает их из файлов Wikimedia Commons.
- Свои фотографии: JPEG или PNG в папке `Изображения/Раскраски` (до версии
  4.1 — `~/Раскраски`, переносится сама); раскраска из
  фотографии готовится в фоне, около полуминуты.
- «+ Добавить»: своя картинка из «Изображений» (или из любой папки через
  «Другая папка…») или поиск картин в Wikidata по художнику, названию или сюжету (и
  по-русски), картинки с Wikimedia Commons; предпросмотр раскраски в трёх
  размерах областей (около 300, 600 и 1000) и загрузка выбранных в галерею.

## Как делаются раскраски

`pbn.py` превращает картинку в области: сводит её к 18–28 цветам (k-means
в пространстве Lab), сливает слишком мелкие и узкие области с соседями,
обводит общие границы и сглаживает их, ставит номер в самое широкое место
области. Результат — SVG в gzip (`.svgz`), по пути на область. Алгоритм
повторяет шаги [paintbynumbersgenerator](https://github.com/drake7707/paintbynumbersgenerator)
(MIT). Картинки чужих приложений-раскрасок не используются: они
принадлежат их авторам.

```
python3 pbn.py --level 3 картинка.jpg раскраска.svgz   # 3, 4, 5: около 300, 600, 1000 областей
python3 make-paintings.py CACHE_DIR [slug...]           # встроенные картины заново
```

## Установка

**Ubuntu 24.04, Debian 13** (и elementary OS 8, Linux Mint 22) — из
репозитория apt Haltia:

```
sudo curl -fsSLo /usr/share/keyrings/haltia-archive-keyring.gpg https://haltia-de.github.io/packages/apt/haltia-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/haltia-archive-keyring.gpg] https://haltia-de.github.io/packages/apt $(. /etc/os-release; echo $VERSION_CODENAME) main" | sudo tee /etc/apt/sources.list.d/haltia.list
sudo apt update && sudo apt install haltia-paint
```

**Flatpak** (любой дистрибутив; среда GNOME — с Flathub):

```
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak remote-add --if-not-exists haltia https://haltia-de.github.io/packages/flatpak/haltia.flatpakrepo
flatpak install haltia io.github.haltia_de.Paint
```

В Flatpak программа видит только «Изображения»: свои фотографии кладите в
`Изображения/Раскраски`, готовые картины сохраняются в
`Изображения/Мои раскраски`; картинку из другой папки можно открыть через
«+ Добавить» → «Взять из галереи» → «Другая папка…». Прогресс лежит в
`~/.var/app/io.github.haltia_de.Paint/data/haltia-paint/`.

**Alpine и postmarketOS** — пакет `haltia-paint` из
[репозитория apk Haltia](https://github.com/haltia-de/packages).

**Из исходников:** нужны Python 3, GTK 3, PyGObject, pycairo, Pillow,
[haltia-kit](https://github.com/haltia-de/kit), а для своих фотографий и
«+ Добавить» ещё numpy и scipy. В Alpine:

```
apk add python3 py3-gobject3 gtk+3.0 py3-cairo py3-pillow py3-numpy py3-scipy py3-haltia-kit
```

Проверенные версии пакетов Python (для Flatpak, где они ставятся колёсами)
— в `requirements.txt`. Поставить в систему (нужен root):

```
sh install.sh                 # в /usr/local
sh install.sh /mnt/root       # в другой корень, например при сборке образа
sh install.sh "$pkgdir" /usr  # с префиксом /usr, как в пакете
```

`install.sh [ROOT] [PREFIX]` кладёт программу в `PREFIX/bin/haltia-paint`,
генератор в `PREFIX/lib/haltia-paint/pbn.py`, картины в
`PREFIX/share/haltia-paint/`, `.desktop`-файл, значок hicolor и metainfo.
Прежние имена до версии 5.0 остаются: команда `b8k-paint` — ссылка на
`haltia-paint`, скрытый `io.github.trudenboy.Paint.desktop`. Старый раздел
оболочки (`/usr/local/share/b8k/apps.d/paint.conf`) и картины версии 2
убирает.

Сборка пакетов: `packaging/alpine/APKBUILD`, `debian/` и
`packaging/flatpak/`, выпуск по тегу — `haltia-de/ci`.

## Оболочка планшета

Программа сделана для оболочки
[device-lenovo-b8000h](https://github.com/haltia-de/device-lenovo-b8000h)
(Linux на Lenovo YOGA Tablet 10 B8000-H), её сборка ставит программу
отсюда по тегу. С оболочкой она связана только стандартами freedesktop:
`.desktop`-файл с `X-B8K-Home=true` и `X-B8K-Replaces` (прежние id `paint` и
`io.github.trudenboy.Paint`) выводит её на домашний экран вместо прежней
кнопки. Без оболочки работает на любом
рабочем столе с GTK 3.

## Лицензия

GPL-2.0, как и вся оболочка (`LICENSE`).
