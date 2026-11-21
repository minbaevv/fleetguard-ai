from __future__ import annotations

import json
import zlib
from pathlib import Path

from PIL import Image

import merge_yolo_datasets
from prepare_dataset import CLASS_INDEX, CLASS_NAMES

BOX = "0 0.5 0.5 0.5 0.5"


def make_image(path: Path) -> None:
    seed = zlib.crc32(str(path).encode("utf-8"))
    color = (seed % 256, (seed >> 8) % 256, (seed >> 16) % 256)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), color).save(path, format="JPEG")


def write_yaml(root: Path, names: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = ["train: train/images", "val: valid/images", "test: test/images", "names:"]
    lines.extend(f"  {index}: {name}" for index, name in enumerate(names))
    (root / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_detection_source(root: Path, names: list[str] | None = None) -> Path:
    write_yaml(root, names or ["crack", "scratch", "dent"])
    return root


def add_extra_image(root: Path, split: str, name: str, label: str | None) -> Path:
    image = root / split / "images" / name
    make_image(image)
    if label is not None:
        label_path = root / split / "labels" / Path(name).with_suffix(".txt")
        label_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.write_text(label + "\n", encoding="utf-8")
    return image


def make_base(root: Path, counts: tuple[int, int, int] = (1, 1, 1)) -> Path:
    for split, count in zip(("train", "val", "test"), counts, strict=True):
        for index in range(count):
            image = root / "images" / split / f"base_{split}_{index}.jpg"
            make_image(image)
            label = root / "labels" / split / f"base_{split}_{index}.txt"
            label.parent.mkdir(parents=True, exist_ok=True)
            label.write_text("0 0.1 0.1 0.4 0.1 0.4 0.4 0.1 0.4\n", encoding="utf-8")
    names = "\n".join(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    (root / "dataset.yaml").write_text(
        "train: images/train\nval: images/val\ntest: images/test\nnames:\n" + names + "\n",
        encoding="utf-8",
    )
    return root


def run(base: Path, extra: list[Path], out: Path, *args: str) -> int:
    argv = ["--base", str(base), "--out", str(out), "--force"]
    for root in extra:
        argv.extend(["--extra", str(root)])
    return merge_yolo_datasets.main([*argv, *args])


def read_label(out: Path, split: str, stem: str) -> list[str]:
    return (out / "labels" / split / f"{stem}.txt").read_text(encoding="utf-8").splitlines()


def report(out: Path) -> dict:
    return json.loads((out / "merge_report.json").read_text(encoding="utf-8"))


def test_bbox_becomes_four_point_polygon(tmp_path: Path) -> None:
    base = make_base(tmp_path / "base")
    extra = make_detection_source(tmp_path / "extra")
    add_extra_image(extra, "train", "box.jpg", "0 0.5 0.5 0.5 0.5")

    assert run(base, [extra], tmp_path / "out") == 0

    lines = read_label(tmp_path / "out", "train", "extra__box")
    assert len(lines) == 1
    parts = lines[0].split()
    assert parts[0] == str(CLASS_INDEX["crack"])
    assert len(parts) == 9
    assert [round(float(value), 4) for value in parts[1:]] == [
        0.25,
        0.25,
        0.75,
        0.25,
        0.75,
        0.75,
        0.25,
        0.75,
    ]


def test_class_aliases_are_mapped_and_unknown_classes_skipped(tmp_path: Path) -> None:
    base = make_base(tmp_path / "base")
    extra = make_detection_source(tmp_path / "extra", ["Glass Shatter", "crack", "rust"])
    add_extra_image(extra, "train", "alias.jpg", "0 0.5 0.5 0.4 0.4")
    add_extra_image(extra, "train", "unknown.jpg", "2 0.5 0.5 0.4 0.4")

    assert run(base, [extra], tmp_path / "out", "--strict") == 1

    alias = read_label(tmp_path / "out", "train", "extra__alias")
    unknown = read_label(tmp_path / "out", "train", "extra__unknown")
    assert alias[0].split()[0] == str(CLASS_INDEX["glass_shatter"])
    assert unknown == []
    assert report(tmp_path / "out")["sources"][1]["unknown_classes"] == ["rust"]


def test_source_splits_are_preserved(tmp_path: Path) -> None:
    base = make_base(tmp_path / "base", (2, 1, 1))
    extra = make_detection_source(tmp_path / "extra")
    add_extra_image(extra, "train", "train.jpg", "0 0.5 0.5 0.2 0.2")
    add_extra_image(extra, "valid", "valid.jpg", "0 0.5 0.5 0.2 0.2")

    assert run(base, [extra], tmp_path / "out") == 0

    data = report(tmp_path / "out")
    assert data["splits"]["train"]["images"] == 3
    assert data["splits"]["val"]["images"] == 2
    assert data["splits"]["test"]["images"] == 1


def test_crack_is_oversampled_only_in_train(tmp_path: Path) -> None:
    base = make_base(tmp_path / "base", (1, 1, 0))
    for split in ("train", "val"):
        label = base / "labels" / split / f"base_{split}_0.txt"
        label.write_text(
            f"{CLASS_INDEX['crack']} 0.1 0.1 0.4 0.1 0.4 0.4 0.1 0.4\n",
            encoding="utf-8",
        )

    assert (
        run(
            base,
            [],
            tmp_path / "out",
            "--oversample-class",
            "crack",
            "--oversample-factor",
            "2",
        )
        == 0
    )

    data = report(tmp_path / "out")
    assert data["splits"]["train"]["images"] == 2
    assert data["splits"]["val"]["images"] == 1
    assert data["oversampled"] == {"class": "crack", "factor": 2, "copies": 1}
    assert read_label(tmp_path / "out", "train", "base_train_0__os1")


def test_duplicate_across_splits_is_kept_in_validation(tmp_path: Path) -> None:
    base = make_base(tmp_path / "base", (1, 1, 0))
    extra = make_detection_source(tmp_path / "extra")
    duplicate = extra / "valid" / "images" / "copy.jpg"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes((base / "images" / "train" / "base_train_0.jpg").read_bytes())
    label = extra / "valid" / "labels" / "copy.txt"
    label.parent.mkdir(parents=True)
    label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    assert run(base, [extra], tmp_path / "out") == 0

    data = report(tmp_path / "out")
    assert data["splits"]["train"]["images"] == 0
    assert data["splits"]["val"]["images"] == 2
    assert len(data["duplicates"]) == 1
    assert (tmp_path / "out" / "images" / "val" / "extra__copy.jpg").is_file()
    assert not (tmp_path / "out" / "images" / "train" / "base_train_0.jpg").exists()


def test_missing_label_becomes_empty_negative(tmp_path: Path) -> None:
    base = make_base(tmp_path / "base")
    extra = make_detection_source(tmp_path / "extra")
    add_extra_image(extra, "train", "negative.jpg", None)

    assert run(base, [extra], tmp_path / "out") == 0

    label = tmp_path / "out" / "labels" / "train" / "extra__negative.txt"
    assert label.is_file()
    assert label.read_text(encoding="utf-8") == ""
    assert report(tmp_path / "out")["totals"]["annotations"] == 3


def test_class_map_overrides_alias_and_targets_project_class(tmp_path: Path) -> None:
    base = make_base(tmp_path / "base")
    extra = make_detection_source(tmp_path / "extra", ["crack", "paint"])
    add_extra_image(extra, "train", "paint.jpg", "1 0.5 0.5 0.3 0.2")
    class_map = tmp_path / "class-map.json"
    class_map.write_text(json.dumps({"paint": "scratch"}), encoding="utf-8")

    assert run(base, [extra], tmp_path / "out", "--class-map", str(class_map)) == 0

    line = read_label(tmp_path / "out", "train", "extra__paint")[0]
    assert line.split()[0] == str(CLASS_INDEX["scratch"])
    assert report(tmp_path / "out")["sources"][1]["mapped_classes"]["1"] == "scratch"
