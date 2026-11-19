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
`--device`, `--project`, `--name`. Результаты складываются в
`cv/runs/yolo11n-seg-baseline/`: `weights/best.pt`, `metrics.md`, `metrics.json`.

`metrics.md` содержит mAP50 и mAP50-95 по маскам и precision/recall по каждому классу. Оценка идёт
только на `val`; test-сплит не используется. Перед запуском проверяется `dataset.yaml`: классы
`0..N-1`, полигоны в `0..1`, у каждого изображения есть `.txt`, лишних меток нет.

### Обучение в Google Colab

Готовый ноутбук: `cv/training/cardd_colab.ipynb`. Полный цикл на бесплатном T4: скачивание ~4 ГБ,
подготовка 10–20 минут, обучение 100 эпох с early stopping — 1–3 часа. Локальный GPU не нужен.

1. Открыть `cardd_colab.ipynb` в Colab: `File → Upload notebook` либо
   `File → Open notebook → GitHub` → `minbaevv/fleetguard-ai`.
2. `Среда выполнения → Сменить среду выполнения → T4 GPU`.
3. `Среда выполнения → Выполнить все`, разрешить доступ к Google Drive.

Ноутбук клонирует репозиторий, скачивает CarDD, собирает разметку из трёх COCO-файлов, готовит
YOLO-seg датасет, проверяет его, обучает и складывает `metrics.md`, `metrics.json`, `best.pt` на
Drive в `fleetguard-cv/runs/yolo11n-seg-cardd`.

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

Забрать артефакты: `metrics.md`, `metrics.json`, `weights/best.pt` и sha256 весов. Метрики и ссылка
на веса публикуются в этом файле после прогона.

### Статус Д2

Реальный прогон ещё не выполнен: официальный CarDD выдаётся по заявке и письму авторам, поэтому
используется публичное зеркало Hugging Face (лицензия CarDD — только исследования, коммерческое
использование требует разрешения авторов). Ноутбук и инструкция готовы, измеренных метрик пока нет.
После прогона нужно опубликовать `metrics.md`, ссылку и sha256 `best.pt` в разделе «Правила».

## Правила

- Веса (`*.pt`, `*.pth`, `*.onnx`) в git не коммитятся.
- Ссылка на скачивание и контрольная сумма весов публикуются здесь после обучения.
- Разбиение train / val / test = 70 / 15 / 15; test не используется для подбора порогов.
- Перед публикацией проверьте лицензию датасета: открытые наборы повреждений часто разрешены
  только для исследований.
