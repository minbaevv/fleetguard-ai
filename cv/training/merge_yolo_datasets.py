"""Merge YOLO datasets into an existing YOLO-seg dataset.

The base dataset keeps its deterministic train/val/test split. Extra sources
keep their own split, class names are mapped to the project schema, detection
boxes are converted to four-point polygons, and images duplicated across
splits are dropped to keep validation honest. Training images of one class can
be oversampled without touching val/test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, UnidentifiedImageError

from prepare_dataset import (
    CLASS_ALIASES,
    CLASS_INDEX,
    CLASS_NAMES,
    load_class_overrides,
    normalize_category,
)

SPLITS = ("train", "val", "test")
SPLIT_ALIASES = {"train": ("train",), "val": ("valid", "val"), "test": ("test",)}
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"})
MIN_POLYGON_AREA = 1e-6
ORIGIN_PREFERENCE = {"base": 0}
SPLIT_PREFERENCE = {"test": 0, "val": 1, "train": 2}


@dataclass
class Sample:
    image: Path
    label_lines: list[str] = field(default_factory=list)
    split: str = "train"
    origin: str = "base"
    name: str = ""
    digest: str = ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_names(path: Path) -> dict[int, str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    names = raw.get("names")
    if isinstance(names, list):
        mapping = {index: str(name) for index, name in enumerate(names)}
    elif isinstance(names, dict):
        mapping = {int(key): str(value) for key, value in names.items()}
    else:
        raise ValueError(f"{path}: names must be a list or a mapping")
    if not mapping or set(mapping) != set(range(len(mapping))):
        raise ValueError(f"{path}: class ids must be 0..N-1")
    return mapping


def find_dataset_yaml(root: Path) -> Path:
    for name in ("data.yaml", "dataset.yaml"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    raise ValueError(f"{root}: data.yaml or dataset.yaml not found")


def build_class_map(names: dict[int, str], overrides: dict[str, int]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for class_id, name in names.items():
        key = normalize_category(name)
        target = overrides.get(key, CLASS_INDEX.get(CLASS_ALIASES.get(key, "")))
        if target is not None:
            mapping[class_id] = target
    return mapping


def locate_split(root: Path, split: str) -> tuple[Path, Path] | None:
    for alias in SPLIT_ALIASES[split]:
        images = root / alias / "images"
        if images.is_dir():
            return images, root / alias / "labels"
    images = root / "images" / split
    if images.is_dir():
        return images, root / "labels" / split
    return None


def polygon_area(values: list[float]) -> float:
    points = list(zip(values[0::2], values[1::2], strict=True))
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def clamp_pairs(values: list[float]) -> list[float]:
    return [min(max(value, 0.0), 1.0) for value in values]


def bbox_to_polygon(values: list[float]) -> list[float] | None:
    center_x, center_y, width, height = values
    if width <= 0 or height <= 0:
        return None
    x1 = min(max(center_x - width / 2, 0.0), 1.0)
    y1 = min(max(center_y - height / 2, 0.0), 1.0)
    x2 = min(max(center_x + width / 2, 0.0), 1.0)
    y2 = min(max(center_y + height / 2, 0.0), 1.0)
    if x2 - x1 < 1e-6 or y2 - y1 < 1e-6:
        return None
    return [x1, y1, x2, y1, x2, y2, x1, y2]


def parse_label(
    path: Path,
    mapping: dict[int, int],
    stats: Counter[str],
    problems: list[str],
    used_unknown: set[int],
) -> list[str]:
    lines: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        tokens = raw.split()
        if not tokens:
            continue
        try:
            class_id = int(tokens[0])
        except ValueError:
            problems.append(f"{path.name}:{number}: class id is not an integer")
            continue
        target = mapping.get(class_id)
        if target is None:
            stats["unknown_class"] += 1
            used_unknown.add(class_id)
            continue
        try:
            values = [float(token) for token in tokens[1:]]
        except ValueError:
            problems.append(f"{path.name}:{number}: coordinate is not a number")
            continue
        if not all(math.isfinite(value) for value in values):
            problems.append(f"{path.name}:{number}: coordinate is not finite")
            continue
        if len(values) == 4:
            polygon = bbox_to_polygon(values)
        elif len(values) >= 6 and len(values) % 2 == 0:
            polygon = clamp_pairs(values)
        else:
            problems.append(f"{path.name}:{number}: expected bbox or polygon")
            continue
        if polygon is None or polygon_area(polygon) < MIN_POLYGON_AREA:
            stats["degenerate"] += 1
            continue
        coordinates = " ".join(f"{value:.6f}" for value in polygon)
        lines.append(f"{target} {coordinates}")
    return lines


def validate_image(path: Path) -> str | None:
    try:
        with Image.open(path) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        return str(error)
    return None


def collect_source(
    root: Path,
    origin: str,
    overrides: dict[str, int],
    report: dict[str, Any],
    check_images: bool,
) -> list[Sample]:
    yaml_path = find_dataset_yaml(root)
    names = load_names(yaml_path)
    mapping = build_class_map(names, overrides)
    unmapped = sorted(class_id for class_id in names if class_id not in mapping)
    stats: Counter[str] = Counter()
    problems: list[str] = []
    samples: list[Sample] = []
    used_unknown: set[int] = set()

    for split in SPLITS:
        located = locate_split(root, split)
        if located is None:
            continue
        images_dir, labels_dir = located
        for image in sorted(images_dir.rglob("*")):
            if not image.is_file() or image.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            label = labels_dir / image.relative_to(images_dir).with_suffix(".txt")
            if label.is_file():
                try:
                    lines = parse_label(label, mapping, stats, problems, used_unknown)
                except (OSError, UnicodeDecodeError) as error:
                    problems.append(f"{label}: {error}")
                    continue
            else:
                lines = []
                stats["missing_label"] += 1
            if check_images and (error := validate_image(image)) is not None:
                problems.append(f"{image.name}: broken image: {error}")
                continue
            name = image.name if origin == "base" else f"{origin}__{image.name}"
            samples.append(
                Sample(image=image, label_lines=lines, split=split, origin=origin, name=name)
            )

    report["sources"].append(
        {
            "root": str(root),
            "origin": origin,
            "classes": names,
            "mapped_classes": {
                class_id: CLASS_NAMES[target] for class_id, target in mapping.items()
            },
            "unmapped_classes": [names[class_id] for class_id in unmapped],
            "unknown_classes": [
                names[class_id] for class_id in sorted(used_unknown) if class_id in names
            ],
            "images": len(samples),
            "labels": dict(sorted(stats.items())),
            "problems": problems,
        }
    )
    return samples


def drop_duplicates(samples: list[Sample], report: dict[str, Any]) -> list[Sample]:
    by_digest: dict[str, Sample] = {}
    dropped: list[dict[str, str]] = []
    ordered = sorted(
        samples,
        key=lambda item: (item.origin, SPLIT_PREFERENCE[item.split], item.name),
    )
    for sample in ordered:
        sample.digest = sha256_file(sample.image)
        incumbent = by_digest.get(sample.digest)
        if incumbent is None:
            by_digest[sample.digest] = sample
            continue
        better = (
            SPLIT_PREFERENCE[sample.split],
            ORIGIN_PREFERENCE.get(sample.origin, 1),
        ) < (
            SPLIT_PREFERENCE[incumbent.split],
            ORIGIN_PREFERENCE.get(incumbent.origin, 1),
        )
        if better:
            dropped.append(
                {
                    "kept": str(incumbent.image),
                    "dropped": str(sample.image),
                    "reason": "duplicate_in_better_split",
                }
            )
            by_digest[sample.digest] = sample
        else:
            dropped.append(
                {
                    "kept": str(incumbent.image),
                    "dropped": str(sample.image),
                    "reason": "duplicate",
                }
            )
    report["duplicates"] = dropped
    return list(by_digest.values())


def unique_name(out_dir: Path, split: str, name: str) -> str:
    candidate = Path(name)
    counter = 1
    while (out_dir / "images" / split / candidate).exists():
        counter += 1
        candidate = Path(f"{candidate.stem}__{counter}{candidate.suffix}")
    return candidate.as_posix()


def link_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def write_sample(out_dir: Path, sample: Sample) -> None:
    sample.name = unique_name(out_dir, sample.split, sample.name)
    image_path = out_dir / "images" / sample.split / sample.name
    label_path = out_dir / "labels" / sample.split / Path(sample.name).with_suffix(".txt")
    link_or_copy(sample.image, image_path)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.write_text("".join(f"{line}\n" for line in sample.label_lines), encoding="utf-8")


def oversample(out_dir: Path, class_name: str, factor: int, report: dict[str, Any]) -> None:
    report["oversampled"] = {"class": class_name, "factor": factor, "copies": 0}
    if factor < 2:
        return
    class_id = CLASS_INDEX[class_name]
    copies = 0
    for image in sorted((out_dir / "images" / "train").glob("*")):
        label = out_dir / "labels" / "train" / f"{image.stem}.txt"
        if not label.is_file():
            continue
        lines = [line.split() for line in label.read_text(encoding="utf-8").splitlines()]
        class_ids = {int(parts[0]) for parts in lines if parts}
        if class_id not in class_ids:
            continue
        for copy_index in range(1, factor):
            suffix = f"__os{copy_index}"
            target_image = image.with_name(f"{image.stem}{suffix}{image.suffix}")
            target_label = label.with_name(f"{label.stem}{suffix}.txt")
            link_or_copy(image, target_image)
            shutil.copy2(label, target_label)
            copies += 1
    report["oversampled"]["copies"] = copies


def summarize_dataset(out_dir: Path) -> dict[str, Any]:
    splits: dict[str, Any] = {
        split: {"images": 0, "annotations": 0, "class_counts": {}} for split in SPLITS
    }
    totals: Counter[str] = Counter()
    for split in SPLITS:
        for label in sorted((out_dir / "labels" / split).glob("*.txt")):
            stats = splits[split]
            stats["images"] += 1
            lines = [line.split() for line in label.read_text(encoding="utf-8").splitlines()]
            annotations = [parts for parts in lines if parts]
            stats["annotations"] += len(annotations)
            for parts in annotations:
                class_name = CLASS_NAMES[int(parts[0])]
                totals[class_name] += 1
                counts = stats["class_counts"]
                counts[class_name] = counts.get(class_name, 0) + 1
    return {
        "splits": splits,
        "totals": {
            "images": sum(splits[split]["images"] for split in SPLITS),
            "annotations": sum(splits[split]["annotations"] for split in SPLITS),
            "class_counts": dict(sorted(totals.items())),
        },
    }


def render_yaml() -> str:
    lines = [
        "# Generated by cv/training/merge_yolo_datasets.py",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    lines.extend(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    return "\n".join(lines) + "\n"


def ensure_output_dir(out_dir: Path, force: bool) -> None:
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise ValueError(f"{out_dir} is not empty, pass --force to overwrite generated files")
    if not force:
        return
    for path in (out_dir / "images", out_dir / "labels"):
        if path.is_dir():
            shutil.rmtree(path)
    for name in ("dataset.yaml", "merge_report.json"):
        path = out_dir / name
        if path.exists():
            path.unlink()


def merge_datasets(
    base: Path,
    extra: list[Path],
    out_dir: Path,
    *,
    force: bool = False,
    class_map_path: Path | None = None,
    oversample_class: str | None = None,
    oversample_factor: int = 2,
) -> dict[str, Any]:
    overrides = load_class_overrides(class_map_path) if class_map_path else {}
    report: dict[str, Any] = {
        "base": str(base),
        "extra": [str(path) for path in extra],
        "sources": [],
        "duplicates": [],
        "oversampled": None,
    }

    samples = collect_source(base, "base", overrides, report, check_images=False)
    if not samples:
        raise ValueError(f"{base}: no images found")
    for root in extra:
        samples.extend(collect_source(root, root.name, overrides, report, check_images=True))

    samples = drop_duplicates(samples, report)

    ensure_output_dir(out_dir, force)
    for split in SPLITS:
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)
    for sample in samples:
        write_sample(out_dir, sample)

    if oversample_class:
        oversample(out_dir, oversample_class, oversample_factor, report)

    report.update(summarize_dataset(out_dir))
    (out_dir / "dataset.yaml").write_text(render_yaml(), encoding="utf-8")
    (out_dir / "merge_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="existing YOLO-seg dataset")
    parser.add_argument(
        "--extra",
        type=Path,
        action="append",
        default=[],
        help="YOLO dataset to add (repeatable)",
    )
    parser.add_argument("--out", type=Path, required=True, help="output dataset directory")
    parser.add_argument(
        "--class-map", type=Path, help="JSON object mapping source names to classes"
    )
    parser.add_argument("--oversample-class", choices=CLASS_NAMES)
    parser.add_argument("--oversample-factor", type=int, default=2)
    parser.add_argument(
        "--force", action="store_true", help="overwrite generated files in a non-empty output"
    )
    parser.add_argument(
        "--strict", action="store_true", help="exit with code 1 when any entry was skipped"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = merge_datasets(
            args.base,
            args.extra,
            args.out,
            force=args.force,
            class_map_path=args.class_map,
            oversample_class=args.oversample_class,
            oversample_factor=args.oversample_factor,
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    splits = report["splits"]
    print(
        "images: "
        + ", ".join(f"{split} {splits[split]['images']}" for split in SPLITS)
        + f"; annotations: {report['totals']['annotations']}"
    )
    classes = report["totals"]["class_counts"]
    print("classes: " + ", ".join(f"{name} {count}" for name, count in classes.items()))
    if report["oversampled"]:
        stats = report["oversampled"]
        print(f"oversampled: {stats['class']} x{stats['factor']} (+{stats['copies']} train copies)")
    print(f"report: {args.out / 'merge_report.json'}")

    unknown = [name for source in report["sources"] for name in source["unknown_classes"]]
    problems = [problem for source in report["sources"] for problem in source["problems"]]
    if unknown or problems:
        print(
            f"skipped: {len(unknown)} unknown classes, {len(problems)} label problems",
            file=sys.stderr,
        )
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
