# Данные и веса модели

Каталог для скриптов подготовки датасета, обучения и оценки. Датасеты и веса в git не коммитятся
(`datasets/` и `cv/weights/` в `.gitignore`).

## Подготовка датасета

`prepare_dataset.py` принимает COCO-разметку с полигонами и раскладывает её в формат YOLO-seg:

```bash
python cv/training/prepare_dataset.py \
  --images datasets/car-damage/images \
  --annotations datasets/car-damage/annotations/instances.json \
  --out datasets/car-damage-yolo
```

Скрипт:

- проверяет каждый файл через Pillow: битые, пустые и отсутствующие изображения попадают в отчёт;
- переводит абсолютные пиксельные полигоны в нормализованные координаты `0..1`, обрезает выход за
  границы кадра и отбрасывает вырожденные полигоны;
- поддерживает шесть классов: `dent`, `scratch`, `crack`, `glass_shatter`, `lamp_broken`,
  `tire_flat`;
- делит изображения на `train` / `val` / `test` = 70 / 15 / 15 детерминированно по `--seed`
  (по умолчанию 42);
- пишет `prepare_report.json` со счётчиками, пропусками и причинами.

RLE-маски не поддерживаются: для них нужен COCO polygon. Если названия категорий в источнике
отличаются, передайте `--class-map mapping.json` вида
`{"broken headlight": "lamp_broken"}`. Безымянные категории и чужие `image_id` пропускаются.

Выходная структура:

```
dataset.yaml
images/{train,val,test}/...
labels/{train,val,test}/...   # один polygon на строку: class x1 y1 x2 y2 ...
prepare_report.json
```

Изображение без валидных полигонов остаётся в датасете с пустым `.txt` (негативный пример) и
считается в `negative_images`. С `--strict` скрипт возвращает код 1, если были пропуски; без флага
он завершается успешно и оставляет разбор в отчёте. Непустой `--out` перезаписывается только с
`--force`, посторонние файлы в каталоге сохраняются.

Проверки: `cd cv && pytest`, `ruff check .`, `ruff format --check .`.

## Обучение

`train.py` проверяет датасет и запускает дообучение `yolo11n-seg` по конфигу
`configs/yolo11n-seg.yaml`: 100 эпох, 640 px, batch 16, seed 42.

Сначала сухой прогон — без GPU и без Ultralytics:

```bash
python cv/training/train.py --data datasets/car-damage-yolo --dry-run
```

Реальное обучение на Colab/Kaggle с GPU:

```bash
pip install -r cv/requirements-train.txt
python cv/training/train.py --data datasets/car-damage-yolo
```

Параметры переопределяются флагами `--model`, `--epochs`, `--imgsz`, `--batch`, `--seed`,
`--device`, `--time-hours`, `--project`, `--name`. Результаты складываются в
`cv/runs/yolo11n-seg-baseline/`: `weights/best.pt`, `metrics.md`, `metrics.json`.

Прогресс печатается в stdout по строке на эпоху: номер, темп, ETA и `mask mAP50-95`. Это сделано
специально для Colab/Kaggle, где вывод `tqdm` легко потерять и кажется, что обучение зависло.

`--time-hours` — мягкий лимит: обучение останавливается после текущей эпохи, а `metrics.md`
честно помечает прогон как незавершённый (`закрыто эпох: N из 100`). Число закрытых эпох всегда
берётся из `results.csv`, а не из аргументов запуска.

`--resume` продолжает прогон из `<project>/<name>/weights/last.pt`. Ultralytics восстанавливает
каталог сохранения из чекпоинта, поэтому возобновляйте только прогон, начатый в том же каталоге.

`metrics.md` содержит mAP50 и mAP50-95 по маскам и precision/recall по каждому классу. Оценка идёт
только на `val`; test-сплит не используется. Перед запуском проверяется `dataset.yaml`: классы
`0..N-1`, полигоны в `0..1`, у каждого изображения есть `.txt`, лишних меток нет.

### Обучение в Kaggle (рекомендуется для merged-датасета)

Готовый ноутбук: `cv/training/cardd_kaggle.ipynb`. Kaggle даёт 30 GPU-часов в неделю и сессию до
12 часов, поэтому 100 эпох реально закрываются за один прогон, а не обрываются на 95-й.

1. Создать новый Notebook и загрузить `cardd_kaggle.ipynb` (`File → Import Notebook`).
2. `Settings → Accelerator → GPU T4 x2` (одна T4 тоже работает, но 100 эпох не успеют).
3. `Settings → Internet → On`.
4. `Add-ons → Secrets` → добавить секрет `ROBOFLOW_API_KEY` со своим ключом Roboflow.
5. `Run → Run all`.

Ноутбук делает то же, что Colab-версия, плюс:

- `USE_BOTH_GPUS = True` включает DDP на двух T4. `batch` остаётся 16, а Ultralytics делит его
  между GPU (`batch_size = batch // world_size`), поэтому эффективный батч совпадает с прогоном на
  одной карте и метрики сравнимы;
- прогресс печатается каждые 30 секунд из `results.csv` — под DDP колбэки родительского процесса
  не срабатывают, а файл пишется всегда;
- `TIME_BUDGET_H` (по умолчанию 10 ч) останавливает обучение до лимита сессии через `SIGINT` всей
  группе процессов, чтобы `best.pt` и `last.pt` успели сохраниться;
- чекпоинт из другого каталога (например, с Colab) не переиспользуется: сверяется `args.yaml`.

Baseline на merged val считается, если положить старый `best.pt` в `/kaggle/input` как Kaggle
Dataset. Иначе ячейка сообщит, что сравнивать не с чем.

Артефакты остаются в `/kaggle/working/fleetguard-ai/runs/yolo11n-seg-cardd-carvengers` и доступны
в правой панели `Output` после `Save Version`.

### Обучение в Google Colab

Готовый ноутбук: `cv/training/cardd_colab.ipynb`. Полный цикл на бесплатном T4: скачивание ~4 ГБ,
подготовка 15–25 минут, обучение 100 эпох с early stopping — 2–4 часа. Локальный GPU не нужен.

**Важно про merged-датасет:** на ~21k изображений эпоха занимает ~7 минут на одной T4, то есть
100 эпох — это ~11–12 часов. Бесплатная сессия Colab (до 12 ч) обрывается раньше финиша, поэтому
для полного прогона используйте Kaggle (ниже) или `--resume` после обрыва.

Прямая ссылка:
<https://colab.research.google.com/github/minbaevv/fleetguard-ai/blob/master/cv/training/cardd_colab.ipynb>

1. Открыть `cardd_colab.ipynb` в Colab по ссылке выше либо через
   `File → Open notebook → GitHub` → `minbaevv/fleetguard-ai`.
2. `Среда выполнения → Сменить среду выполнения → T4 GPU`.
3. Получить бесплатный ключ Roboflow: `universe.roboflow.com` → войти → `Settings` → `API Keys`.
4. `Среда выполнения → Выполнить все`, вставить ключ Roboflow в появившееся поле, разрешить доступ
   к Google Drive.

Ноутбук клонирует репозиторий, скачивает CarDD (4000 изображений) и Carvengers (17293 изображения,
боксы), собирает разметку, готовит YOLO-seg датасет, домешивает Carvengers с oversampling `crack`,
проверяет датасет, обучает и складывает `metrics.md`, `metrics.json`, `best.pt` на Drive в
`fleetguard-cv/runs/yolo11n-seg-cardd-carvengers`. Перед обучением он оценивает baseline `best.pt`
на том же merged val, поэтому сравнение до/после идёт на одной выборке.

Если Colab пишет «Блокнот не найден»:

- Colab забирает файл через GitHub API, а анонимный лимит — 60 запросов в час на IP. Нажмите
  «Запросить авторизацию в GitHub» либо скачайте файл и загрузите через `File → Upload notebook`.
- Кнопка `Download raw file` на странице GitHub сохраняет имя `cardd_colab.ipynb`; прямая raw-ссылка
  может сохраниться как `.ipynb.txt` — переименуйте файл перед загрузкой.

Вручную те же шаги:

```bash
!git clone https://github.com/minbaevv/fleetguard-ai.git
%cd fleetguard-ai
!pip -q install ultralytics huggingface_hub
```

```python
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="shawnmichael/CarDD",
    repo_type="dataset",
    local_dir="datasets/cardd",
    allow_patterns=[
        "images/train/*.jpg",
        "images/val/*.jpg",
        "images/test/*.jpg",
        "annotations/instances_*.json",
    ],
    max_workers=8,
)
```

Зеркало содержит все 4000 изображений (2816 train / 810 val / 374 test) и три COCO-файла. Каталоги
`images/*` раскладываются в один по имени файла: имена уникальны, `image_id` в JSON пересекаются,
поэтому разметка объединяется через `merge_coco_splits.py`.

```python
import os
from pathlib import Path

base = Path("datasets/cardd")
flat = base / "images_all"
flat.mkdir(parents=True, exist_ok=True)
for split in ("train", "val", "test"):
    for image in (base / "images" / split).glob("*.jpg"):
        target = flat / image.name
        if not target.exists():
            os.link(image, target)
print(len(list(flat.glob("*.jpg"))), "images")
```

```bash
!python cv/training/merge_coco_splits.py \
  --annotations datasets/cardd/annotations/instances_train2017.json \
                datasets/cardd/annotations/instances_val2017.json \
                datasets/cardd/annotations/instances_test2017.json \
  --out datasets/cardd/instances_all.json
!python cv/training/prepare_dataset.py \
  --images datasets/cardd/images_all \
  --annotations datasets/cardd/instances_all.json \
  --out datasets/cardd-yolo \
  --seed 42
!python cv/training/train.py --data datasets/cardd-yolo --dry-run
```

```bash
!python cv/training/train.py \
  --data datasets/cardd-yolo \
  --device 0 \
  --project /content/drive/MyDrive/fleetguard-cv/runs \
  --name yolo11n-seg-cardd
```

Забрать артефакты: `metrics.md`, `metrics.json`, `weights/best.pt` и sha256 весов.

### Результаты обучения

Прогон 100 эпох на T4: `yolo11n-seg.pt`, датасет CarDD, seed 42. Метрики сняты `model.val()` на
`val`; test-сплит не использовался.

| Класс | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| all | 0.7383 | 0.6939 | 0.7138 | 0.5444 |
| dent | 0.6810 | 0.5584 | 0.5918 | 0.3097 |
| scratch | 0.5877 | 0.5808 | 0.5802 | 0.2984 |
| crack | 0.4833 | 0.2836 | 0.2779 | 0.1035 |
| glass_shatter | 0.9397 | 0.9564 | 0.9907 | 0.9193 |
| lamp_broken | 0.7980 | 0.8522 | 0.8658 | 0.6951 |
| tire_flat | 0.9403 | 0.9318 | 0.9767 | 0.9407 |

- веса: [best.pt](https://drive.google.com/file/d/1yKpH56q9Ite_PyncHD6vjy2E63mPkU-u/view?usp=sharing),
  6.0 MB;
- sha256: `d6e78445115c1d25dff88b962bbe6412aca4eb9e413aca24cb0d1a1ac115facb` (сверено с локальной
  копией файла).

Крупные повреждения находятся уверенно, мелкие — плохо: `crack` mAP50 0.28, `scratch` и `dent` по
0.58. Причина — тонкие объекты и мало примеров `crack` в CarDD. Следующий шаг: домешивание внешнего
датасета и oversampling `crack`.

### Улучшение мелких классов: Carvengers

Второй источник —
[carvengers-damage-detection](https://universe.roboflow.com/carvengers/carvengers-damage-detection)
(17293 изображения, версия 1, экспорт YOLOv8, лицензия **CC BY 4.0**, автор Carvengers). Это
**object detection**: боксы переводятся в прямоугольные полигоны, поэтому маски для этих
изображений грубее полигональных масок CarDD.

Скачать датасет можно только с бесплатным ключом Roboflow (`Settings → API Keys`):

```python
from roboflow import Roboflow

project = Roboflow(api_key="...").workspace("carvengers").project("carvengers-damage-detection")
project.version(2).download("yolov8", location="datasets/carvengers")
```

**Берите версию 2.** На странице датасета это 17293 изображения с классами проекта
(`crack, scratch, dent, glass_shatter, lamp_broken, tire_flat`). Прогон на версии 1 дал
`12 unknown classes`: таксономия не совпала, все аннотации Carvengers отбросились, а 17158
изображений записались пустыми label — то есть «фон без повреждений». Обучение на таком датасете
учит модель, что повреждений нет.

Слияние с подготовленным CarDD (путь к каталогу, где лежит `data.yaml`):

```bash
python cv/training/merge_yolo_datasets.py \
  --base datasets/cardd-yolo \
  --extra datasets/carvengers \
  --out datasets/cardd-carvengers-yolo \
  --oversample-class crack \
  --oversample-factor 2
python cv/training/train.py --data datasets/cardd-carvengers-yolo --dry-run
python cv/training/train.py \
  --data datasets/cardd-carvengers-yolo \
  --device 0 \
  --project /content/drive/MyDrive/fleetguard-cv/runs \
  --name yolo11n-seg-cardd-carvengers
```

Скрипт:

- приводит классы к `dent, scratch, crack, glass_shatter, lamp_broken, tire_flat` по именам и
  алиасам (`glass-shatter`, `Glass Shatter`, `flat tyre` и т. п.);
- конвертирует `class cx cy w h` в 4-точечный полигон и обрезает координаты в `0..1`;
- сохраняет сплиты источников: CarDD — 70/15/15 (seed 42), Carvengers — train/valid/test из экспорта;
- удаляет точные дубликаты по sha256 с приоритетом val/test, чтобы не завышать метрики;
- дублирует изображения с `crack` только в train (`--oversample-factor 2`), val/test не меняются;
- отбрасывает изображение, если **все** его аннотации отброшены (несмапленный класс или битая
  геометрия): пустой label сделал бы его негативом и научил модель, что повреждений нет;
- отказывается сливать источник, у которого не смапилась ни одна аннотация. Такой источник даёт
  только фон; чтобы слить его намеренно, нужен `--allow-unannotated-source`;
- пишет `merge_report.json`: счётчики по классам, число аннотаций и отброшенных изображений по
  каждому источнику, неизвестные классы, дубликаты, число копий.

Повторный прогон — с `--force`. Неизвестные классы и битые метки не роняют процесс; `--strict`
делает их ошибкой.

**Статус:** код и ноутбук готовы, обучение на объединённом датасете ещё не выполнено. Метрики
появятся здесь только после реального прогона `model.val()`.

Лицензии: CarDD — исследовательская/некоммерческая (для коммерческого использования нужно разрешение
авторов); Carvengers — CC BY 4.0, требуется указание авторства Carvengers / Roboflow Universe.

### Статус Д2

Выполнен: обучение прошло на публичном зеркале CarDD (`shawnmichael/CarDD`, 4000 изображений), метрики
и веса опубликованы выше. Официальная выдача CarDD идёт по заявке авторам; лицензия набора —
исследовательская/некоммерческая, коммерческое использование требует разрешения авторов.

## Правила

- Веса (`*.pt`, `*.pth`, `*.onnx`) в git не коммитятся.
- Ссылка на скачивание и контрольная сумма весов публикуются здесь после обучения.
- Разбиение train / val / test = 70 / 15 / 15; test не используется для подбора порогов.
- Перед публикацией проверьте лицензию датасета: открытые наборы повреждений часто разрешены
  только для исследований.
- При использовании двух источников указывайте оба и их лицензии: CarDD — исследовательская,
  Carvengers — CC BY 4.0 (автор Carvengers / Roboflow Universe).
