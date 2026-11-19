"""Convert COCO polygon annotations into a YOLO-seg dataset.

The script validates images and annotations instead of trusting the source,
normalizes absolute pixel polygons, and performs a deterministic 70/15/15
split. Every rejected entry is written to ``prepare_report.json``.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

CLASS_NAMES = (
    "dent",
    "scratch",
    "crack",
    "glass_shatter",
    "lamp_broken",
    "tire_flat",
)
CLASS_INDEX = {name: index for index, name in enumerate(CLASS_NAMES)}

CLASS_ALIASES = {
    "dent": "dent",
    "scratch": "scratch",
    "crack": "crack",
    "glass shatter": "glass_shatter",
    "shatter": "glass_shatter",
    "broken glass": "glass_shatter",
    "broken lamp": "lamp_broken",
    "lamp broken": "lamp_broken",
    "broken headlight": "lamp_broken",
    "flat tire": "tire_flat",
    "tire flat": "tire_flat",
    "flat tyre": "tire_flat",
}

MIN_POLYGON_AREA = 1e-6
SPLITS = ("train", "val", "test")


@dataclass(frozen=True)
class ImageEntry:
    image_id: int
    file_name: str
    relative_path: Path
    source_path: Path
    width: int
    height: int


@dataclass
class PreparedDataset:
    images: dict[int, ImageEntry]
    labels: dict[int, list[str]]
    skipped_images: list[dict[str, Any]]
    skipped_annotations: list[dict[str, Any]]
    unknown_categories: list[str]
    seed: int


def normalize_category(value: str) -> str:
    return " ".join(value.replace("_", " ").replace("-", " ").lower().split())


def load_coco(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    for key in ("images", "annotations", "categories"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"{path}: missing or invalid '{key}'")
    return data


def load_class_overrides(path: Path) -> dict[str, int]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: class map must be a JSON object")
    overrides: dict[str, int] = {}
    for source, target in data.items():
        if not isinstance(target, str) or target not in CLASS_INDEX:
            raise ValueError(f"{path}: unknown target class {target!r} for {source!r}")
        overrides[normalize_category(str(source))] = CLASS_INDEX[target]
    return overrides


def resolve_categories(
    categories: list[dict[str, Any]], overrides: dict[str, int]
) -> tuple[dict[int, int], list[tuple[int, str]]]:
    mapping: dict[int, int] = {}
    unknown: list[tuple[int, str]] = []
    for category in categories:
        category_id = category.get("id")
        name = category.get("name")
        if not isinstance(category_id, int) or not isinstance(name, str):
            continue
        key = normalize_category(name)
        class_index = overrides.get(key, CLASS_INDEX.get(CLASS_ALIASES.get(key, "")))
        if class_index is None:
            unknown.append((category_id, name))
            continue
        mapping[category_id] = class_index
    return mapping, unknown


def safe_relative_path(file_name: str) -> Path:
    path = Path(file_name)
    if path.is_absolute() or path.drive or any(part == ".." for part in path.parts):
        raise ValueError("absolute or parent path")
    parts = [part for part in path.parts if part not in ("", ".")]
    if not parts:
        raise ValueError("empty file name")
    return Path(*parts)


def probe_image(path: Path) -> tuple[int, int]:
    if not path.is_file():
        raise ValueError("file not found")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("empty image")
    return width, height


def collect_images(
    images_dir: Path, raw_images: list[dict[str, Any]], skipped: list[dict[str, Any]]
) -> dict[int, ImageEntry]:
    images: dict[int, ImageEntry] = {}
    seen: set[Path] = set()
    stems: set[Path] = set()
    for raw in raw_images:
        image_id = raw.get("id")
        file_name = raw.get("file_name")
        if not isinstance(image_id, int) or not isinstance(file_name, str):
            skipped.append(
                {"id": image_id, "file_name": file_name, "reason": "invalid_image_entry"}
            )
            continue
        try:
            relative_path = safe_relative_path(file_name)
        except ValueError:
            skipped.append({"id": image_id, "file_name": file_name, "reason": "unsafe_path"})
            continue
        if relative_path in seen:
            skipped.append(
                {"id": image_id, "file_name": file_name, "reason": "duplicate_file_name"}
            )
            continue
        stem = relative_path.with_suffix("")
        if stem in stems:
            skipped.append(
                {"id": image_id, "file_name": file_name, "reason": "duplicate_label_name"}
            )
            continue

        source_path = images_dir / relative_path
        try:
            width, height = probe_image(source_path)
        except (
            UnidentifiedImageError,
            OSError,
            SyntaxError,
            ValueError,
            Image.DecompressionBombError,
        ) as error:
            skipped.append(
                {"id": image_id, "file_name": file_name, "reason": f"broken_image: {error}"}
            )
            continue

        seen.add(relative_path)
        stems.add(stem)
        images[image_id] = ImageEntry(
            image_id=image_id,
            file_name=file_name,
            relative_path=relative_path,
            source_path=source_path,
            width=width,
            height=height,
        )
    return images


def normalized_polygon(
    values: list[Any], width: int, height: int
) -> list[tuple[float, float]] | None:
    if len(values) < 6 or len(values) % 2:
        return None

    points: list[tuple[float, float]] = []
    for index in range(0, len(values), 2):
        x, y = values[index], values[index + 1]
        if isinstance(x, bool) or isinstance(y, bool):
            return None
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None
        x, y = float(x), float(y)
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        points.append((min(max(x, 0.0), width) / width, min(max(y, 0.0), height) / height))

    if polygon_area(points) < MIN_POLYGON_AREA:
        return None
    return points


def polygon_area(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def collect_labels(
    raw_annotations: list[dict[str, Any]],
    images: dict[int, ImageEntry],
    category_map: dict[int, int],
    skipped: list[dict[str, Any]],
) -> dict[int, list[str]]:
    labels: dict[int, list[str]] = {image_id: [] for image_id in images}
    for raw in raw_annotations:
        annotation_id = raw.get("id")
        image_id = raw.get("image_id")
        category_id = raw.get("category_id")

        if image_id not in images:
            skipped.append({"id": annotation_id, "image_id": image_id, "reason": "unknown_image"})
            continue
        class_index = category_map.get(category_id)
        if class_index is None:
            skipped.append(
                {"id": annotation_id, "image_id": image_id, "reason": "unmapped_category"}
            )
            continue
        if raw.get("iscrowd") == 1:
            skipped.append(
                {"id": annotation_id, "image_id": image_id, "reason": "crowd_annotation"}
            )
            continue

        segmentation = raw.get("segmentation")
        if not isinstance(segmentation, list):
            skipped.append(
                {"id": annotation_id, "image_id": image_id, "reason": "rle_not_supported"}
            )
            continue

        entry = images[image_id]
        lines: list[str] = []
        for polygon in segmentation:
            if not isinstance(polygon, list):
                continue
            points = normalized_polygon(polygon, entry.width, entry.height)
            if points is None:
                continue
            coordinates = " ".join(f"{value:.6f}" for point in points for value in point)
            lines.append(f"{class_index} {coordinates}")

        if not lines:
            skipped.append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "reason": "no_valid_polygon",
                }
            )
            continue
        labels[image_id].extend(lines)
    return labels


def assign_splits(images: dict[int, ImageEntry], seed: int) -> dict[int, str]:
    ordered = sorted(images.values(), key=lambda entry: entry.relative_path.as_posix())
    image_ids = [entry.image_id for entry in ordered]
    random.Random(seed).shuffle(image_ids)  # noqa: S311 - reproducibility, not security

    total = len(image_ids)
    if total >= 7:
        train_count = round(total * 0.70)
        val_count = round(total * 0.15)
        test_count = total - train_count - val_count
    else:
        train_count, val_count, test_count = total, 0, 0
    if min(train_count, val_count, test_count) < 1:
        train_count, val_count, test_count = total, 0, 0

    assignments: dict[int, str] = {}
    for index, image_id in enumerate(image_ids):
        if index < train_count:
            assignments[image_id] = "train"
        elif index < train_count + val_count:
            assignments[image_id] = "val"
        else:
            assignments[image_id] = "test"
    return assignments


def render_dataset_yaml() -> str:
    lines = [
        "# Generated by cv/training/prepare_dataset.py",
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
    for name in ("dataset.yaml", "prepare_report.json"):
        path = out_dir / name
        if path.exists():
            path.unlink()


def write_dataset(out_dir: Path, prepared: PreparedDataset, assignments: dict[int, str]) -> None:
    for split in SPLITS:
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    for image_id, entry in prepared.images.items():
        split = assignments[image_id]
        image_path = out_dir / "images" / split / entry.relative_path
        image_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry.source_path, image_path)

        label_path = out_dir / "labels" / split / entry.relative_path.with_suffix(".txt")
        label_path.parent.mkdir(parents=True, exist_ok=True)
        lines = prepared.labels[image_id]
        label_path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")

    (out_dir / "dataset.yaml").write_text(render_dataset_yaml(), encoding="utf-8")


def build_report(
    prepared: PreparedDataset,
    assignments: dict[int, str],
    images_dir: Path,
    annotations_path: Path,
) -> dict[str, Any]:
    split_stats: dict[str, Any] = {
        split: {"images": 0, "annotations": 0, "class_counts": {}} for split in SPLITS
    }
    total_counts: Counter[str] = Counter()
    negative_images = 0

    for image_id in prepared.images:
        split = assignments[image_id]
        lines = prepared.labels[image_id]
        split_stats[split]["images"] += 1
        split_stats[split]["annotations"] += len(lines)
        if not lines:
            negative_images += 1
        for line in lines:
            class_name = CLASS_NAMES[int(line.split()[0])]
            total_counts[class_name] += 1
            split_counts = split_stats[split]["class_counts"]
            split_counts[class_name] = split_counts.get(class_name, 0) + 1

    ok = not (
        prepared.skipped_images or prepared.skipped_annotations or prepared.unknown_categories
    )
    return {
        "ok": ok,
        "seed": prepared.seed,
        "source": {
            "images": str(images_dir),
            "annotations": str(annotations_path),
        },
        "splits": split_stats,
        "totals": {
            "images": len(prepared.images),
            "negative_images": negative_images,
            "annotations": sum(len(lines) for lines in prepared.labels.values()),
            "class_counts": dict(sorted(total_counts.items())),
        },
        "skipped": {
            "images": prepared.skipped_images,
            "annotations": prepared.skipped_annotations,
            "unknown_categories": prepared.unknown_categories,
        },
    }


def prepare_dataset(
    images_dir: Path,
    annotations_path: Path,
    out_dir: Path,
    *,
    seed: int = 42,
    force: bool = False,
    class_map_path: Path | None = None,
) -> dict[str, Any]:
    coco = load_coco(annotations_path)
    overrides = load_class_overrides(class_map_path) if class_map_path else {}

    skipped_images: list[dict[str, Any]] = []
    skipped_annotations: list[dict[str, Any]] = []

    images = collect_images(images_dir, coco["images"], skipped_images)
    if not images:
        raise ValueError("no valid images found")

    category_map, unknown = resolve_categories(coco["categories"], overrides)
    labels = collect_labels(coco["annotations"], images, category_map, skipped_annotations)

    unmapped_ids = {category_id for category_id, _ in unknown}
    used_unmapped = {
        raw.get("category_id")
        for raw in coco["annotations"]
        if raw.get("category_id") in unmapped_ids
    }
    unknown_categories = sorted(
        {name for category_id, name in unknown if category_id in used_unmapped}
    )

    prepared = PreparedDataset(
        images=images,
        labels=labels,
        skipped_images=skipped_images,
        skipped_annotations=skipped_annotations,
        unknown_categories=unknown_categories,
        seed=seed,
    )
    assignments = assign_splits(images, seed)

    ensure_output_dir(out_dir, force)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_dataset(out_dir, prepared, assignments)
    report = build_report(prepared, assignments, images_dir, annotations_path)
    (out_dir / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True, help="directory with source images")
    parser.add_argument("--annotations", type=Path, required=True, help="COCO JSON file")
    parser.add_argument("--out", type=Path, required=True, help="output dataset directory")
    parser.add_argument("--seed", type=int, default=42, help="split seed (default: 42)")
    parser.add_argument(
        "--class-map",
        type=Path,
        help="JSON object mapping source category names to target class names",
    )
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
        report = prepare_dataset(
            args.images,
            args.annotations,
            args.out,
            seed=args.seed,
            force=args.force,
            class_map_path=args.class_map,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    splits = report["splits"]
    print(
        "images: "
        f"{report['totals']['images']} kept, {len(report['skipped']['images'])} skipped; "
        f"annotations: {report['totals']['annotations']} kept, "
        f"{len(report['skipped']['annotations'])} skipped"
    )
    print(
        "splits: "
        + ", ".join(f"{split} {splits[split]['images']}" for split in SPLITS)
        + f"; report: {args.out / 'prepare_report.json'}"
    )
    if report["ok"]:
        return 0
    if args.strict:
        print("strict: skipped entries found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
