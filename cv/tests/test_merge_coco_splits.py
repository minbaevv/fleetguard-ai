from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import merge_coco_splits

CATEGORIES = [
    {"id": 1, "name": "dent"},
    {"id": 2, "name": "scratch"},
]


def build_split(split: str, names: list[str], category_id: int = 1) -> dict[str, Any]:
    images = [
        {"id": index, "file_name": name, "width": 640, "height": 480}
        for index, name in enumerate(names, start=1)
    ]
    annotations = [
        {
            "id": index,
            "image_id": index,
            "category_id": category_id,
            "segmentation": [[10, 10, 40, 10, 40, 40]],
            "iscrowd": 0,
        }
        for index in range(1, len(names) + 1)
    ]
    return {"images": images, "annotations": annotations, "categories": CATEGORIES}


def dump(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_merge_remaps_colliding_ids_and_keeps_file_names(tmp_path: Path) -> None:
    train = dump(tmp_path / "train.json", build_split("train", ["000001.jpg", "000002.jpg"]))
    val = dump(tmp_path / "val.json", build_split("val", ["000003.jpg"]))

    merged = merge_coco_splits.merge_coco([train, val])

    assert [image["id"] for image in merged["images"]] == [1, 2, 3]
    assert [image["file_name"] for image in merged["images"]] == [
        "000001.jpg",
        "000002.jpg",
        "000003.jpg",
    ]
    assert [annotation["id"] for annotation in merged["annotations"]] == [1, 2, 3]
    assert [annotation["image_id"] for annotation in merged["annotations"]] == [1, 2, 3]
    assert len(merged["categories"]) == 2


def test_merge_rejects_duplicate_file_names(tmp_path: Path) -> None:
    first = dump(tmp_path / "first.json", build_split("train", ["000001.jpg"]))
    second = dump(tmp_path / "second.json", build_split("val", ["000001.jpg"]))

    try:
        merge_coco_splits.merge_coco([first, second])
    except ValueError as error:
        assert "duplicate image file name" in str(error)
    else:
        raise AssertionError("duplicate file name was accepted")


def test_merge_rejects_annotation_with_unknown_image(tmp_path: Path) -> None:
    data = build_split("train", ["000001.jpg"])
    data["annotations"][0]["image_id"] = 99
    path = dump(tmp_path / "broken.json", data)

    try:
        merge_coco_splits.merge_coco([path])
    except ValueError as error:
        assert "unknown image" in str(error)
    else:
        raise AssertionError("orphan annotation was accepted")


def test_merge_rejects_conflicting_category_names(tmp_path: Path) -> None:
    first = build_split("train", ["000001.jpg"])
    second = build_split("val", ["000002.jpg"])
    second["categories"] = [{"id": 1, "name": "scratch"}]
    paths = [dump(tmp_path / "first.json", first), dump(tmp_path / "second.json", second)]

    try:
        merge_coco_splits.merge_coco(paths)
    except ValueError as error:
        assert "conflicting name" in str(error)
    else:
        raise AssertionError("conflicting category name was accepted")


def test_cli_writes_merged_file(tmp_path: Path) -> None:
    train = dump(tmp_path / "train.json", build_split("train", ["000001.jpg"]))
    val = dump(tmp_path / "val.json", build_split("val", ["000002.jpg"]))
    out = tmp_path / "nested" / "instances_all.json"

    code = merge_coco_splits.main(["--annotations", str(train), str(val), "--out", str(out)])

    assert code == 0
    merged = json.loads(out.read_text(encoding="utf-8"))
    assert len(merged["images"]) == 2
    assert len(merged["annotations"]) == 2


def test_cli_reports_missing_file(tmp_path: Path) -> None:
    code = merge_coco_splits.main(
        ["--annotations", str(tmp_path / "missing.json"), "--out", str(tmp_path / "out.json")]
    )

    assert code == 2
