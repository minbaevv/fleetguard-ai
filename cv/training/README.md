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

Прямая ссылка:
<https://colab.research.google.com/github/minbaevv/fleetguard-ai/blob/master/cv/training/cardd_colab.ipynb>

1. Открыть `cardd_colab.ipynb` в Colab по ссылке выше либо через
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
