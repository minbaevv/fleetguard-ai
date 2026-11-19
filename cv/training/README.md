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

Полный цикл на бесплатном T4: скачивание ~4 ГБ, подготовка ~3 минуты, обучение 100 эпох с early
stopping — ориентировочно 2–4 часа. Локальный GPU не нужен.

1. `Среда выполнения → Сменить среду выполнения → T4 GPU`.

2. Клонировать репозиторий и поставить зависимости:

   ```bash
   !git clone https://github.com/minbaevv/fleetguard-ai.git
   %cd fleetguard-ai
   !pip -q install ultralytics huggingface_hub
   ```

3. Скачать CarDD (официальный COCO-релиз, зеркало Hugging Face):

   ```python
   from huggingface_hub import snapshot_download

   snapshot_download(
       repo_id="Vishwa-307/CarDD",
       repo_type="dataset",
       local_dir="datasets/cardd",
       allow_patterns=[
           "CarDD_release/CarDD_release/CarDD_COCO/annotations/instances_*.json",
           "CarDD_release/CarDD_release/CarDD_COCO/train2017/*.jpg",
           "CarDD_release/CarDD_release/CarDD_COCO/val2017/*.jpg",
           "CarDD_release/CarDD_release/CarDD_COCO/test2017/*.jpg",
       ],
       max_workers=8,
   )
   ```

4. Собрать изображения в один каталог (жёсткие ссылки, без копирования) и объединить разметку:
   `image_id` в трёх JSON пересекаются, поэтому нужен `merge_coco_splits.py`.

   ```python
   import os
   from pathlib import Path

   coco = Path("datasets/cardd/CarDD_release/CarDD_release/CarDD_COCO")
   flat = Path("datasets/cardd/images_all")
   flat.mkdir(parents=True, exist_ok=True)
   for split in ("train2017", "val2017", "test2017"):
       for image in (coco / split).glob("*.jpg"):
           target = flat / image.name
           if not target.exists():
               os.link(image, target)
   print(len(list(flat.glob("*.jpg"))), "images")
   ```

   ```bash
   !python cv/training/merge_coco_splits.py \
     --annotations datasets/cardd/CarDD_release/CarDD_release/CarDD_COCO/annotations/instances_train2017.json \
                   datasets/cardd/CarDD_release/CarDD_release/CarDD_COCO/annotations/instances_val2017.json \
                   datasets/cardd/CarDD_release/CarDD_release/CarDD_COCO/annotations/instances_test2017.json \
     --out datasets/cardd/instances_all.json
   ```

5. Подготовить YOLO-seg датасет и проверить его до обучения:

   ```bash
   !python cv/training/prepare_dataset.py \
     --images datasets/cardd/images_all \
     --annotations datasets/cardd/instances_all.json \
     --out datasets/cardd-yolo \
     --seed 42
   !python cv/training/train.py --data datasets/cardd-yolo --dry-run
   ```

6. Запустить обучение. Чекпоинты сразу пишутся на Google Drive, чтобы пережить разрыв сессии:

   ```bash
   !python cv/training/train.py \
     --data datasets/cardd-yolo \
     --device 0 \
     --project /content/drive/MyDrive/fleetguard-cv \
     --name yolo11n-seg-cardd
   ```

   Если Drive ещё не подключён, выполните `from google.colab import drive; drive.mount("/content/drive")`
   или уберите `--project`, чтобы писать в `cv/runs/`.

7. Забрать артефакты: `metrics.md`, `metrics.json`, `weights/best.pt` и `sha256sum best.pt`.
   Метрики и ссылка на веса публикуются в этом файле после прогона.

### Статус Д2

Реальный прогон ещё не выполнен: официальный CarDD выдаётся по заявке и письму авторам, поэтому
для обучения используется публичное зеркало Hugging Face (лицензия CarDD — только исследования,
см. `CarDD_license.pdf` в датасете). Инструкция выше готова, измеренных метрик пока нет. После
прогона нужно опубликовать `metrics.md`, ссылку и sha256 `best.pt` в разделе «Правила».

## Правила

- Веса (`*.pt`, `*.pth`, `*.onnx`) в git не коммитятся.
- Ссылка на скачивание и контрольная сумма весов публикуются здесь после обучения.
- Разбиение train / val / test = 70 / 15 / 15; test не используется для подбора порогов.
- Перед публикацией проверьте лицензию датасета: открытые наборы повреждений часто разрешены
  только для исследований.
