from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

import prepare_dataset

CLASS_NAMES = prepare_dataset.CLASS_NAMES


def make_image(path: Path, size: tuple[int, int] = (120, 90)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (190, 190, 190)).save(path, format="JPEG")


def square(x: int = 10, y: int = 10, size: int = 20) -> list[int]:
    return [x, y, x + size, y, x + size, y + size, x, y + size]


def dump_coco(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def build_source(tmp_path: Path, count: int) -> tuple[Path, Path, dict[str, Any]]:
    images_dir = tmp_path / "source" / "images"
    images_dir.mkdir(parents=True)
    categories = [{"id": index, "name": name} for index, name in enumerate(CLASS_NAMES, start=1)]
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    for index in range(count):
        name = f"car_{index:02d}.jpg"
        make_image(images_dir / name)
        image_id = index + 1
        images.append({"id": image_id, "file_name": name, "width": 120, "height": 90})
        annotations.append(
            {
                "id": image_id,
                "image_id": image_id,
                "category_id": index % len(CLASS_NAMES) + 1,
                "segmentation": [square(10 + index, 15)],
            }
        )
    data = {"images": images, "annotations": annotations, "categories": categories}
    annotations_path = tmp_path / "source" / "instances.json"
    dump_coco(annotations_path, data)
    return images_dir, annotations_path, data


def read_report(out_dir: Path) -> dict[str, Any]:
    return json.loads((out_dir / "prepare_report.json").read_text(encoding="utf-8"))


def run(
    images_dir: Path,
    annotations_path: Path,
    out_dir: Path,
    *extra: str,
) -> int:
    return prepare_dataset.main(
        [
            "--images",
            str(images_dir),
            "--annotations",
            str(annotations_path),
            "--out",
            str(out_dir),
            *extra,
        ]
    )


def test_split_is_deterministic_and_polygons_are_normalized(tmp_path: Path) -> None:
    images_dir, annotations_path, _ = build_source(tmp_path, 20)
    out_a = tmp_path / "out-a"
    out_b = tmp_path / "out-b"

    assert run(images_dir, annotations_path, out_a) == 0
    assert run(images_dir, annotations_path, out_b) == 0

    report = read_report(out_a)
    assert report["ok"] is True
    assert report["totals"]["images"] == 20
    assert report["totals"]["annotations"] == 20
    assert report["splits"]["train"]["images"] == 14
    assert report["splits"]["val"]["images"] == 3
    assert report["splits"]["test"]["images"] == 3
    assert sorted(report["totals"]["class_counts"]) == sorted(CLASS_NAMES)

    labels_a = sorted(
        path.relative_to(out_a / "labels") for path in (out_a / "labels").rglob("*.txt")
    )
    labels_b = sorted(
        path.relative_to(out_b / "labels") for path in (out_b / "labels").rglob("*.txt")
    )
    assert labels_a == labels_b
    assert len(labels_a) == 20
    for relative in labels_a:
        assert (out_a / "labels" / relative).read_text() == (
            out_b / "labels" / relative
        ).read_text()

    lines = [
        line
        for path in (out_a / "labels").rglob("*.txt")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(lines) == 20
    assert all(line.split()[0].isdigit() for line in lines)
    assert all(0.0 <= float(value) <= 1.0 for line in lines for value in line.split()[1:])

    dataset_yaml = (out_a / "dataset.yaml").read_text(encoding="utf-8")
    assert "train: images/train" in dataset_yaml
    assert "val: images/val" in dataset_yaml
    assert "test: images/test" in dataset_yaml
    for name in CLASS_NAMES:
        assert f": {name}" in dataset_yaml


def test_broken_and_missing_images_are_reported(tmp_path: Path) -> None:
    images_dir, annotations_path, data = build_source(tmp_path, 2)
    (images_dir / "broken.jpg").write_bytes(b"not an image")
    data["images"].extend(
        [
            {"id": 3, "file_name": "broken.jpg", "width": 120, "height": 90},
            {"id": 4, "file_name": "missing.jpg", "width": 120, "height": 90},
        ]
    )
    dump_coco(annotations_path, data)
    out_dir = tmp_path / "out"

    assert run(images_dir, annotations_path, out_dir, "--strict") == 1

    report = read_report(out_dir)
    reasons = [item["reason"] for item in report["skipped"]["images"]]
    assert len(reasons) == 2
    assert any(reason.startswith("broken_image") for reason in reasons)
    assert any("file not found" in reason for reason in reasons)
    assert report["totals"]["images"] == 2
    assert len(list((out_dir / "images").rglob("*.jpg"))) == 2


def test_invalid_annotations_are_skipped(tmp_path: Path) -> None:
    images_dir, annotations_path, data = build_source(tmp_path, 2)
    data["categories"].append({"id": 99, "name": "hood"})
    data["annotations"] = [
        {"id": 1, "image_id": 1, "category_id": 1, "segmentation": {"counts": "x"}},
        {"id": 2, "image_id": 1, "category_id": 1, "segmentation": [square()[:4]]},
        {"id": 3, "image_id": 1, "category_id": 1, "segmentation": [[10, 10] * 4]},
        {"id": 4, "image_id": 1, "category_id": 99, "segmentation": [square()]},
        {"id": 5, "image_id": 2, "category_id": 2, "segmentation": [square()]},
    ]
    dump_coco(annotations_path, data)
    out_dir = tmp_path / "out"

    assert run(images_dir, annotations_path, out_dir, "--strict") == 1

    report = read_report(out_dir)
    reasons = [item["reason"] for item in report["skipped"]["annotations"]]
    assert reasons.count("rle_not_supported") == 1
    assert reasons.count("no_valid_polygon") == 2
    assert reasons.count("unmapped_category") == 1
    assert report["skipped"]["unknown_categories"] == ["hood"]
    assert report["totals"]["annotations"] == 1
    assert report["totals"]["negative_images"] == 1

    label_files = list((out_dir / "labels").rglob("*.txt"))
    assert len(label_files) == 2
    non_empty = [path for path in label_files if path.read_text(encoding="utf-8").strip()]
    assert len(non_empty) == 1
    assert non_empty[0].read_text(encoding="utf-8").startswith("1 ")


def test_unsafe_image_path_is_skipped(tmp_path: Path) -> None:
    images_dir, annotations_path, data = build_source(tmp_path, 1)
    data["images"].append({"id": 2, "file_name": "../escape.jpg", "width": 10, "height": 10})
    data["images"].append(
        {"id": 3, "file_name": str(tmp_path / "absolute.jpg"), "width": 10, "height": 10}
    )
    dump_coco(annotations_path, data)
    out_dir = tmp_path / "out"

    assert run(images_dir, annotations_path, out_dir, "--strict") == 1

    report = read_report(out_dir)
    assert [item["reason"] for item in report["skipped"]["images"]] == ["unsafe_path"] * 2
    assert not (tmp_path / "escape.jpg").exists()
    assert report["totals"]["images"] == 1


def test_duplicate_label_stem_is_rejected(tmp_path: Path) -> None:
    images_dir, annotations_path, data = build_source(tmp_path, 1)
    make_image(images_dir / "car_00.png")
    data["images"].append({"id": 2, "file_name": "car_00.png", "width": 120, "height": 90})
    dump_coco(annotations_path, data)
    out_dir = tmp_path / "out"

    assert run(images_dir, annotations_path, out_dir, "--strict") == 1

    report = read_report(out_dir)
    assert [item["reason"] for item in report["skipped"]["images"]] == ["duplicate_label_name"]
    assert report["totals"]["images"] == 1
    assert len(list((out_dir / "images").rglob("*.*"))) == 1


def test_non_empty_output_requires_force(tmp_path: Path) -> None:
    images_dir, annotations_path, _ = build_source(tmp_path, 2)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "keep.txt").write_text("keep", encoding="utf-8")

    assert run(images_dir, annotations_path, out_dir) == 2
    assert (out_dir / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not (out_dir / "dataset.yaml").exists()

    assert run(images_dir, annotations_path, out_dir, "--force") == 0
    assert (out_dir / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert (out_dir / "dataset.yaml").exists()


def test_polygon_is_clamped_to_image_bounds(tmp_path: Path) -> None:
    images_dir = tmp_path / "source" / "images"
    make_image(images_dir / "wide.jpg", size=(100, 50))
    data = {
        "images": [{"id": 1, "file_name": "wide.jpg", "width": 100, "height": 50}],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 1,
                "segmentation": [[-20, -20, 300, -20, 300, 200, -20, 200]],
            }
        ],
        "categories": [{"id": 1, "name": "dent"}],
    }
    annotations_path = tmp_path / "source" / "instances.json"
    dump_coco(annotations_path, data)
    out_dir = tmp_path / "out"

    assert run(images_dir, annotations_path, out_dir) == 0

    label = next((out_dir / "labels").rglob("*.txt")).read_text(encoding="utf-8")
    values = [float(value) for value in label.split()[1:]]
    assert min(values) == 0.0
    assert max(values) == 1.0


def test_class_map_override_maps_custom_category(tmp_path: Path) -> None:
    images_dir, annotations_path, data = build_source(tmp_path, 1)
    data["categories"][0]["name"] = "Повреждение кузова"
    dump_coco(annotations_path, data)
    class_map = tmp_path / "class-map.json"
    class_map.write_text(json.dumps({"повреждение кузова": "scratch"}), encoding="utf-8")
    out_dir = tmp_path / "out"

    assert (
        run(
            images_dir,
            annotations_path,
            out_dir,
            "--class-map",
            str(class_map),
            "--strict",
        )
        == 0
    )

    label = next((out_dir / "labels").rglob("*.txt")).read_text(encoding="utf-8")
    assert label.startswith(f"{CLASS_NAMES.index('scratch')} ")
