"""Train YOLO-seg on a prepared dataset and export measured metrics.

The harness validates the dataset before touching the GPU, never evaluates on
the test split, and keeps Ultralytics optional so ``--dry-run`` works without
torch installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).resolve().parent / "configs" / "yolo11n-seg.yaml"

SPLITS = ("train", "val", "test")
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"})
DATASET_YAML_NAMES = ("dataset.yaml", "data.yaml")
MIN_POLYGON_POINTS = 3

OVERALL_KEYS = {
    "precision": "metrics/precision(M)",
    "recall": "metrics/recall(M)",
    "map50": "metrics/mAP50(M)",
    "map50_95": "metrics/mAP50-95(M)",
}


@dataclass(frozen=True)
class TrainConfig:
    model: str = "yolo11n-seg.pt"
    epochs: int = 100
    imgsz: int = 640
    batch: int = 16
    patience: int = 20
    seed: int = 42
    workers: int = 4
    optimizer: str = "auto"
    device: str | None = None
    time_hours: float | None = None
    project: Path = Path("cv/runs")
    name: str = "yolo11n-seg-baseline"


@dataclass(frozen=True)
class SplitSummary:
    name: str
    images: int
    annotations: int
    negative_images: int


@dataclass(frozen=True)
class DatasetSummary:
    root: Path
    yaml_path: Path
    names: dict[int, str]
    splits: dict[str, SplitSummary]

    def describe(self) -> list[str]:
        classes = ", ".join(self.names[index] for index in sorted(self.names))
        split_text = "; ".join(
            f"{split} {self.splits[split].images} images, "
            f"{self.splits[split].annotations} annotations, "
            f"{self.splits[split].negative_images} negative"
            for split in SPLITS
            if split in self.splits
        )
        return [
            f"dataset: {self.yaml_path}",
            f"classes: {len(self.names)} ({classes})",
            f"splits: {split_text}",
        ]


@dataclass(frozen=True)
class MetricsRow:
    label: str
    precision: float | None
    recall: float | None
    map50: float | None
    map50_95: float | None


def _int(raw: Mapping[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value


def _text(raw: Mapping[str, Any], key: str, default: str) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_text(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value.strip() or None


def _path(raw: Mapping[str, Any], key: str, default: Path) -> Path:
    value = raw.get(key, default)
    if isinstance(value, Path):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty path")
    return Path(value.strip())


def _optional_hours(raw: Mapping[str, Any], key: str, maximum: float) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number or null")
    hours = float(value)
    if not math.isfinite(hours) or not 0 < hours <= maximum:
        raise ValueError(f"{key} must be between 0 and {maximum:g}")
    return hours


def parse_config(raw: Mapping[str, Any]) -> TrainConfig:
    known = {field.name for field in fields(TrainConfig)}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValueError(f"unknown config keys: {', '.join(unknown)}")
    defaults = TrainConfig()
    return TrainConfig(
        model=_text(raw, "model", defaults.model),
        epochs=_int(raw, "epochs", defaults.epochs, 1, 1000),
        imgsz=_int(raw, "imgsz", defaults.imgsz, 32, 4096),
        batch=_int(raw, "batch", defaults.batch, 1, 512),
        patience=_int(raw, "patience", defaults.patience, 1, 1000),
        seed=_int(raw, "seed", defaults.seed, 0, 2**31 - 1),
        workers=_int(raw, "workers", defaults.workers, 0, 32),
        optimizer=_text(raw, "optimizer", defaults.optimizer),
        device=_optional_text(raw, "device"),
        time_hours=_optional_hours(raw, "time_hours", 72.0),
        project=_path(raw, "project", defaults.project),
        name=_text(raw, "name", defaults.name),
    )


def load_config(
    path: Path | None = None, overrides: Mapping[str, Any] | None = None
) -> TrainConfig:
    raw: dict[str, Any] = {}
    if path is not None:
        if not path.is_file():
            raise ValueError(f"config not found: {path}")
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{path}: config must be a mapping")
        raw.update(loaded)
    if overrides:
        raw.update({key: value for key, value in overrides.items() if value is not None})
    return parse_config(raw)


def resolve_project(project: Path) -> Path:
    return project if project.is_absolute() else REPO_ROOT / project


def resolve_dataset_yaml(path: Path) -> Path:
    if path.is_dir():
        for name in DATASET_YAML_NAMES:
            candidate = path / name
            if candidate.is_file():
                return candidate
        raise ValueError(f"{path}: dataset.yaml not found, run prepare_dataset.py first")
    if path.is_file():
        return path
    raise ValueError(f"dataset path not found: {path}")


def _resolve_inside(root: Path, relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError(f"dataset.yaml: {label} must be a non-empty path")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError(f"dataset.yaml: {label} points outside the dataset: {relative}")
    return candidate


def parse_names(raw: Any) -> dict[int, str]:
    if isinstance(raw, list):
        items: list[tuple[Any, Any]] = list(enumerate(raw))
    elif isinstance(raw, dict):
        items = list(raw.items())
    else:
        raise ValueError("dataset.yaml: names must be a list or a mapping")

    names: dict[int, str] = {}
    for class_id, value in items:
        if isinstance(class_id, bool) or not isinstance(class_id, int):
            raise ValueError("dataset.yaml: class ids must be integers")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"dataset.yaml: empty class name for id {class_id}")
        names[class_id] = value.strip()

    if not names:
        raise ValueError("dataset.yaml: no classes")
    if set(names) != set(range(len(names))):
        raise ValueError("dataset.yaml: class ids must be numbered 0..N-1")
    if len(set(names.values())) != len(names):
        raise ValueError("dataset.yaml: class names must be unique")
    return names


def label_dir_for(root: Path, split: str, split_dir: Path) -> Path:
    relative = split_dir.relative_to(root.resolve())
    if relative.parts and relative.parts[0] == "images":
        return root / "labels" / Path(*relative.parts[1:])
    return root / "labels" / split


def parse_label(path: Path, names: Mapping[int, str]) -> tuple[int, list[str]]:
    polygons = 0
    problems: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        tokens = line.split()
        if not tokens:
            continue
        if len(tokens) < 1 + MIN_POLYGON_POINTS * 2:
            problems.append(f"{path.name}:{number}: expected class and at least 3 points")
            continue
        try:
            class_id = int(tokens[0])
        except ValueError:
            problems.append(f"{path.name}:{number}: class id is not an integer")
            continue
        if class_id not in names:
            problems.append(f"{path.name}:{number}: unknown class {class_id}")
            continue
        coordinates = tokens[1:]
        if len(coordinates) % 2:
            problems.append(f"{path.name}:{number}: odd coordinate count")
            continue
        try:
            values = [float(value) for value in coordinates]
        except ValueError:
            problems.append(f"{path.name}:{number}: non-numeric coordinate")
            continue
        if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values):
            problems.append(f"{path.name}:{number}: coordinates must be within 0..1")
            continue
        polygons += 1
    return polygons, problems


def validate_dataset(path: Path) -> DatasetSummary:
    yaml_path = resolve_dataset_yaml(path)
    root = yaml_path.parent
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{yaml_path}: expected a YAML mapping")
    names = parse_names(raw.get("names"))

    problems: list[str] = []
    splits: dict[str, SplitSummary] = {}
    for split in SPLITS:
        relative = raw.get(split)
        if relative is None:
            if split == "test":
                continue
            problems.append(f"missing '{split}' split")
            continue
        split_dir = _resolve_inside(root, relative, split)
        if not split_dir.is_dir():
            problems.append(f"missing '{split}' directory: {relative}")
            continue
        label_dir = label_dir_for(root, split, split_dir)
        images = sorted(
            path
            for path in split_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        if not images:
            problems.append(f"'{split}' split has no images")
            continue

        expected_labels: set[Path] = set()
        annotations = 0
        negative = 0
        for image_path in images:
            label_path = label_dir / image_path.relative_to(split_dir).with_suffix(".txt")
            expected_labels.add(label_path)
            if not label_path.is_file():
                problems.append(f"{split}: missing label for {image_path.name}")
                continue
            try:
                polygons, label_problems = parse_label(label_path, names)
            except (OSError, UnicodeDecodeError) as error:
                problems.append(f"{split}: unreadable label {label_path.name}: {error}")
                continue
            problems.extend(f"{split}: {problem}" for problem in label_problems)
            if polygons:
                annotations += polygons
            else:
                negative += 1

        if label_dir.is_dir():
            for orphan in sorted(label_dir.rglob("*.txt")):
                if orphan not in expected_labels:
                    problems.append(
                        f"{split}: label without image: {orphan.relative_to(label_dir).as_posix()}"
                    )

        splits[split] = SplitSummary(
            name=split,
            images=len(images),
            annotations=annotations,
            negative_images=negative,
        )

    if problems:
        shown = problems[:10]
        message = "\n".join(f"- {problem}" for problem in shown)
        if len(problems) > len(shown):
            message += f"\n- ... and {len(problems) - len(shown)} more"
        raise ValueError(f"dataset is invalid: {yaml_path}\n{message}")

    return DatasetSummary(root=root, yaml_path=yaml_path, names=names, splits=splits)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _at(values: Any, index: int) -> float | None:
    try:
        return _number(values[index])
    except (IndexError, KeyError, TypeError):
        return None


def overall_row(results: Mapping[str, Any]) -> MetricsRow:
    return MetricsRow(
        label="all",
        precision=_number(results.get(OVERALL_KEYS["precision"])),
        recall=_number(results.get(OVERALL_KEYS["recall"])),
        map50=_number(results.get(OVERALL_KEYS["map50"])),
        map50_95=_number(results.get(OVERALL_KEYS["map50_95"])),
    )


def class_rows(metrics: Any, names: Mapping[int, str]) -> list[MetricsRow]:
    seg = getattr(metrics, "seg", None)
    class_ids = getattr(seg, "ap_class_index", None)
    if class_ids is None:
        return []

    rows: list[MetricsRow] = []
    for position, raw_id in enumerate(class_ids):
        name = names.get(int(raw_id))
        if name is None:
            continue
        rows.append(
            MetricsRow(
                label=name,
                precision=_at(getattr(seg, "p", None), position),
                recall=_at(getattr(seg, "r", None), position),
                map50=_at(getattr(seg, "ap50", None), position),
                map50_95=_at(getattr(seg, "ap", None), position),
            )
        )
    return rows


def _format(value: float | None) -> str:
    return "—" if value is None else f"{value:.4f}"


def render_metrics_table(rows: Sequence[MetricsRow]) -> str:
    lines = [
        "| Класс | Precision | Recall | mAP50 | mAP50-95 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        cells = (
            row.label,
            _format(row.precision),
            _format(row.recall),
            _format(row.map50),
            _format(row.map50_95),
        )
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def collect_metrics(
    model: Any, data_path: Path, split: str, names: Mapping[int, str]
) -> dict[str, Any]:
    metrics = model.val(data=str(data_path), split=split)
    results = getattr(metrics, "results_dict", None)
    if not isinstance(results, Mapping):
        results = {}
    overall = overall_row(results)
    classes = class_rows(metrics, names)
    return {
        "split": split,
        "overall": asdict(overall),
        "classes": [asdict(row) for row in classes],
        "markdown": render_metrics_table([overall, *classes]),
    }


def format_duration(seconds: float) -> str:
    total = round(max(seconds, 0.0))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _trainer_metric(trainer: Any, key: str) -> float | None:
    metrics = getattr(trainer, "metrics", None)
    if not isinstance(metrics, Mapping):
        return None
    return _number(metrics.get(key))


class EpochProgress:
    """Print one readable line per epoch and stop cleanly at a time budget.

    Notebook UIs hide tqdm output, so a long run looks frozen without this.
    The line carries the epoch, the measured pace and the remaining time.
    """

    def __init__(
        self,
        total: int,
        stream: Any = None,
        clock: Callable[[], float] = time.monotonic,
        budget_hours: float | None = None,
    ) -> None:
        self.total = total
        self.stream = sys.stdout if stream is None else stream
        self.clock = clock
        self.budget_hours = budget_hours
        self._last_epoch: int | None = None
        self._last_time: float | None = None
        self._started: float | None = None
        self._durations: list[float] = []
        self.stopped_early = False

    def attach(self, model: Any) -> None:
        add_callback = getattr(model, "add_callback", None)
        if callable(add_callback):
            add_callback("on_train_start", self.on_train_start)
            # on_fit_epoch_end runs after validation and after the epoch's weights are
            # written, so the printed mAP belongs to the epoch just finished. A stop
            # flag set here is still honoured by the trainer's loop.
            add_callback("on_fit_epoch_end", self.on_epoch_end)

    def on_train_start(self, trainer: Any) -> None:
        start = int(getattr(trainer, "start_epoch", 0) or 0)
        total = int(getattr(trainer, "epochs", 0) or self.total)
        self._started = self.clock()
        if start:
            print(
                f"resume: continuing at epoch {start + 1}/{total}",
                file=self.stream,
                flush=True,
            )

    def _budget_spent(self) -> bool:
        if not self.budget_hours or self._started is None:
            return False
        return self.clock() - self._started >= self.budget_hours * 3600

    def on_epoch_end(self, trainer: Any) -> None:
        epoch = int(getattr(trainer, "epoch", 0)) + 1
        total = int(getattr(trainer, "epochs", 0) or self.total)
        if total <= 0:
            return

        now = self.clock()
        measured: float | None = None
        if self._last_time is not None and self._last_epoch is not None:
            finished = epoch - self._last_epoch
            if finished > 0:
                measured = (now - self._last_time) / finished
                self._durations.append(measured)
        self._last_epoch, self._last_time = epoch, now

        seconds = measured
        if seconds is None:
            reported = _number(getattr(trainer, "epoch_time", None))
            seconds = reported if reported and reported > 0 else None
        average = sum(self._durations) / len(self._durations) if self._durations else seconds

        parts = [f"epoch {epoch}/{total} ({epoch * 100 // total}%)"]
        if seconds is not None:
            parts.append(f"{format_duration(seconds)}/epoch")
        if average is not None:
            parts.append(f"ETA {format_duration(average * max(total - epoch, 0))}")
        box = _trainer_metric(trainer, "metrics/mAP50-95(B)")
        mask = _trainer_metric(trainer, "metrics/mAP50-95(M)")
        if box is not None:
            parts.append(f"box mAP50-95 {box:.4f}")
        if mask is not None:
            parts.append(f"mask mAP50-95 {mask:.4f}")

        if self._budget_spent() and epoch < total:
            self.stopped_early = True
            trainer.stop = True
            parts.append(f"time budget {self.budget_hours:g}h spent, stopping")
        print(" | ".join(parts), file=self.stream, flush=True)


def build_train_kwargs(config: TrainConfig, data_path: Path) -> dict[str, Any]:
    return {
        "data": str(data_path),
        "epochs": config.epochs,
        "imgsz": config.imgsz,
        "batch": config.batch,
        "patience": config.patience,
        "seed": config.seed,
        "workers": config.workers,
        "optimizer": config.optimizer,
        "device": config.device,
        "project": str(config.project),
        "name": config.name,
        "exist_ok": True,
        "plots": True,
    }


def load_yolo(model_name: str) -> Any:
    try:
        from ultralytics import YOLO
    except ImportError as error:
        raise RuntimeError(
            "ultralytics is not installed: pip install -r cv/requirements-train.txt "
            "or run on Colab with a GPU"
        ) from error
    return YOLO(model_name)


def best_weights(model: Any) -> Path | None:
    candidate = getattr(getattr(model, "trainer", None), "best", None)
    if candidate is None:
        return None
    path = Path(candidate)
    return path if path.is_file() else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_metrics(run_dir: Path, report: Mapping[str, Any], table: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (run_dir / "metrics.json").write_text(payload, encoding="utf-8")

    lines = [
        "# Метрики YOLO-seg",
        "",
        f"- модель: `{report['model']}`",
        f"- датасет: `{report['dataset']}`",
        f"- эпох: {report['epochs']}, seed: {report['seed']}",
        f"- сплит: `{report['split']}` (test не использовался)",
    ]
    if report.get("weights"):
        lines.append(f"- веса: `{report['weights']}`")
        lines.append(f"- sha256: `{report['weights_sha256']}`")
    if report.get("resumed_from"):
        lines.append(f"- продолжено с: `{report['resumed_from']}`")
    if report.get("stopped_early"):
        completed = report.get("epochs_completed")
        if completed is None:
            lines.append("- остановлено по лимиту времени: план эпох не выполнен полностью")
        else:
            lines.append(
                f"- закрыто эпох: {completed} из {report['epochs']} "
                "(прогон остановлен досрочно, метрики не финальные)"
            )
    lines.extend(
        [
            "",
            table,
            "",
            "Таблица построена по `model.val()`; значения округлены до 4 знаков.",
        ]
    )
    (run_dir / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def resume_weights(project: Path, name: str) -> Path:
    return project / name / "weights" / "last.pt"


def completed_epochs(run_dir: Path) -> int | None:
    """Count finished epochs from results.csv.

    Ultralytics writes one row per finished epoch, so this is the only trustworthy
    count when a run stops early or when DDP hides the trainer's own state.
    """
    csv_path = run_dir / "results.csv"
    if not csv_path.is_file():
        return None
    rows = [line for line in csv_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return max(len(rows) - 1, 0)


def run_training(
    config: TrainConfig,
    data: Path,
    *,
    dry_run: bool = False,
    resume: bool = False,
    model_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    summary = validate_dataset(data)
    for line in summary.describe():
        print(line)

    resolved = replace(config, project=resolve_project(config.project))
    weights = resume_weights(resolved.project, config.name) if resume else None
    if weights is not None and not weights.is_file():
        raise ValueError(f"resume checkpoint not found: {weights}")

    plan = build_train_kwargs(resolved, summary.yaml_path)
    if resume:
        plan["resume"] = True

    if dry_run:
        action = f"resume={weights}" if weights else f"model={config.model}"
        print(
            "plan: "
            f"{action} epochs={config.epochs} imgsz={config.imgsz} "
            f"batch={config.batch} seed={config.seed} "
            f"project={plan['project']} name={plan['name']}"
        )
        if config.time_hours:
            print(f"time budget: {config.time_hours:g} h")
        print("dry run: nothing trained, ultralytics not imported")
        return {"status": "dry_run", "plan": plan}

    factory = model_factory or load_yolo
    model = factory(str(weights) if weights else config.model)
    progress = EpochProgress(total=config.epochs, budget_hours=config.time_hours)
    progress.attach(model)
    print(
        f"training: model={weights or config.model} epochs={config.epochs} data={summary.yaml_path}"
    )
    if config.time_hours:
        print(
            f"time budget: {config.time_hours:g} h; "
            "the run stops after the epoch in progress and evaluates best.pt"
        )
    model.train(**plan)

    best = best_weights(model)
    eval_model = factory(str(best)) if best else model
    metrics = collect_metrics(eval_model, summary.yaml_path, "val", summary.names)

    run_dir = resolved.project / config.name
    finished = completed_epochs(run_dir)
    report = {
        "model": config.model,
        "dataset": str(summary.yaml_path),
        "epochs": config.epochs,
        "epochs_completed": finished,
        "seed": config.seed,
        "split": metrics["split"],
        "overall": metrics["overall"],
        "classes": metrics["classes"],
        "weights": str(best) if best else None,
        "weights_sha256": sha256_file(best) if best else None,
        "resumed_from": str(weights) if weights else None,
        "stopped_early": progress.stopped_early
        or (finished is not None and finished < config.epochs),
    }
    write_metrics(run_dir, report, metrics["markdown"])
    print(metrics["markdown"])
    if finished is not None and finished < config.epochs:
        print(f"внимание: закрыто {finished} из {config.epochs} эпох, метрики не финальные")
    print(f"metrics: {run_dir / 'metrics.md'}")
    return report


OVERRIDE_FIELDS = (
    "model",
    "epochs",
    "imgsz",
    "batch",
    "seed",
    "device",
    "time_hours",
    "project",
    "name",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", type=Path, required=True, help="prepared dataset directory or dataset.yaml"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="training config YAML")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate the dataset and print the plan"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue the run in <project>/<name> from weights/last.pt",
    )
    parser.add_argument("--model", help="override model, e.g. yolo11s-seg.pt")
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--imgsz", type=int)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--device", help="cpu, 0 or 0,1; empty means auto")
    parser.add_argument(
        "--time-hours",
        type=float,
        help="stop after this many hours and evaluate the best weights",
    )
    parser.add_argument("--project", type=Path)
    parser.add_argument("--name")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    overrides = {
        key: getattr(args, key) for key in OVERRIDE_FIELDS if getattr(args, key) is not None
    }
    try:
        config = load_config(args.config, overrides)
        run_training(config, args.data, dry_run=args.dry_run, resume=args.resume)
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
