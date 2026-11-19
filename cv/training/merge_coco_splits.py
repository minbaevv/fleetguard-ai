"""Merge COCO split files into one annotation file with unique ids.

CarDD ships three COCO JSON files whose ``image_id`` values restart from 1 in
every split. ``prepare_dataset.py`` accepts a single annotation file, so the
ids must be remapped before the deterministic train/val/test split.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_coco(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    for key in ("images", "annotations", "categories"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"{path}: missing or invalid '{key}'")
    return data


def merge_coco(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        raise ValueError("at least one annotation file is required")

    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    categories: dict[int, dict[str, Any]] = {}
    seen_file_names: set[str] = set()
    next_image_id = 1
    next_annotation_id = 1

    for path in paths:
        data = load_coco(path)
        for category in data["categories"]:
            category_id = category.get("id")
            if not isinstance(category_id, int):
                raise ValueError(f"{path}: category without integer id")
            existing = categories.get(category_id)
            if existing is not None and existing.get("name") != category.get("name"):
                raise ValueError(f"{path}: category {category_id} has a conflicting name")
            categories[category_id] = category

        id_map: dict[int, int] = {}
        for image in data["images"]:
            image_id = image.get("id")
            file_name = image.get("file_name")
            if not isinstance(image_id, int) or not isinstance(file_name, str):
                raise ValueError(f"{path}: image without integer id or file name")
            if file_name in seen_file_names:
                raise ValueError(f"{path}: duplicate image file name {file_name!r}")
            seen_file_names.add(file_name)
            id_map[image_id] = next_image_id
            images.append({**image, "id": next_image_id})
            next_image_id += 1

        for annotation in data["annotations"]:
            image_id = annotation.get("image_id")
            if image_id not in id_map:
                raise ValueError(f"{path}: annotation points to unknown image {image_id!r}")
            annotations.append(
                {
                    **annotation,
                    "id": next_annotation_id,
                    "image_id": id_map[image_id],
                }
            )
            next_annotation_id += 1

    return {
        "images": images,
        "annotations": annotations,
        "categories": list(categories.values()),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--annotations",
        type=Path,
        nargs="+",
        required=True,
        help="COCO JSON files to merge, in order",
    )
    parser.add_argument("--out", type=Path, required=True, help="output COCO JSON file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        merged = merge_coco(args.annotations)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(merged, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"images: {len(merged['images'])}, annotations: {len(merged['annotations'])}, "
        f"categories: {len(merged['categories'])}; out: {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
