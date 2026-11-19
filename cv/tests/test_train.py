from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

import train

NAMES = {0: "dent", 1: "scratch"}
POLYGON = "0 0.1 0.1 0.4 0.1 0.4 0.4 0.1 0.4\n"


def write_yaml(root: Path, data: dict[str, Any]) -> None:
    (root / "dataset.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def read_yaml(root: Path) -> dict[str, Any]:
    return yaml.safe_load((root / "dataset.yaml").read_text(encoding="utf-8"))


def build_dataset(
    tmp_path: Path, *, train_count: int = 4, val_count: int = 2, test_count: int = 2
) -> Path:
    root = tmp_path / "dataset"
    counts = {"train": train_count, "val": val_count, "test": test_count}
    for split, count in counts.items():
        image_dir = root / "images" / split
        label_dir = root / "labels" / split
        image_dir.mkdir(parents=True)
        label_dir.mkdir(parents=True)
        for index in range(count):
            (image_dir / f"{split}_{index}.jpg").write_bytes(b"jpeg")
            (label_dir / f"{split}_{index}.txt").write_text(
                "" if index == 0 else POLYGON, encoding="utf-8"
            )
    write_yaml(
        root,
        {
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "names": NAMES,
        },
    )
    return root


class FakeSeg:
    ap_class_index: ClassVar[list[int]] = [0, 1]
    p: ClassVar[list[float]] = [0.8, 0.6]
    r: ClassVar[list[float]] = [0.7, 0.5]
    ap50: ClassVar[list[float]] = [0.75, 0.55]
    ap: ClassVar[list[float]] = [0.5, 0.3]


class FakeMetrics:
    results_dict: ClassVar[dict[str, float]] = {
        "metrics/precision(M)": 0.7,
        "metrics/recall(M)": 0.6,
        "metrics/mAP50(M)": 0.65,
        "metrics/mAP50-95(M)": 0.4,
    }
    seg: ClassVar[FakeSeg] = FakeSeg()


class FakeTrainer:
    def __init__(self, best: Path) -> None:
        self.best = best


class FakeModel:
    def __init__(self) -> None:
        self.train_calls: list[dict[str, Any]] = []
        self.val_calls: list[dict[str, Any]] = []

    def train(self, **kwargs: Any) -> FakeModel:
        self.train_calls.append(kwargs)
        return self

    def val(self, **kwargs: Any) -> FakeMetrics:
        self.val_calls.append(kwargs)
        return FakeMetrics()


def test_validate_dataset_counts_splits_and_negatives(tmp_path: Path) -> None:
    root = build_dataset(tmp_path)

    summary = train.validate_dataset(root)

    assert summary.names == NAMES
    assert summary.yaml_path == root / "dataset.yaml"
    assert summary.splits["train"] == train.SplitSummary("train", 4, 3, 1)
    assert summary.splits["val"].images == 2
    assert summary.splits["test"].images == 2
    assert any("train 4 images, 3 annotations, 1 negative" in line for line in summary.describe())


def test_validate_dataset_accepts_yaml_path(tmp_path: Path) -> None:
    root = build_dataset(tmp_path)

    summary = train.validate_dataset(root / "dataset.yaml")

    assert summary.root == root


def test_validate_dataset_reports_label_problems(tmp_path: Path) -> None:
    root = build_dataset(tmp_path)
    (root / "labels" / "train" / "train_1.txt").write_text(
        "9 0.1 0.1 0.4 0.1 0.4 0.4\n0 0.1 0.1 0.4\n1 1.5 0.1 0.4 0.1 0.4 0.4\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        train.validate_dataset(root)

    message = str(excinfo.value)
    assert "unknown class 9" in message
    assert "at least 3 points" in message
    assert "within 0..1" in message


def test_validate_dataset_rejects_missing_label(tmp_path: Path) -> None:
    root = build_dataset(tmp_path)
    (root / "labels" / "train" / "train_1.txt").unlink()

    with pytest.raises(ValueError, match=r"missing label for train_1\.jpg"):
        train.validate_dataset(root)


def test_validate_dataset_rejects_orphan_label(tmp_path: Path) -> None:
    root = build_dataset(tmp_path)
    (root / "labels" / "train" / "ghost.txt").write_text(POLYGON, encoding="utf-8")

    with pytest.raises(ValueError, match=r"label without image: ghost\.txt"):
        train.validate_dataset(root)


def test_validate_dataset_requires_train_and_val(tmp_path: Path) -> None:
    root = build_dataset(tmp_path)
    data = read_yaml(root)
    data.pop("train")
    write_yaml(root, data)

    with pytest.raises(ValueError, match="missing 'train' split"):
        train.validate_dataset(root)


def test_split_path_cannot_escape_dataset(tmp_path: Path) -> None:
    root = build_dataset(tmp_path)
    data = read_yaml(root)
    data["train"] = "../outside"
    write_yaml(root, data)

    with pytest.raises(ValueError, match="outside the dataset"):
        train.validate_dataset(root)


def test_names_must_be_contiguous() -> None:
    with pytest.raises(ValueError, match=r"0\.\.N-1"):
        train.parse_names({0: "dent", 2: "scratch"})


def test_parse_names_accepts_list() -> None:
    assert train.parse_names(["dent", "scratch"]) == NAMES


def test_shipped_config_matches_plan() -> None:
    config = train.load_config(train.DEFAULT_CONFIG)

    assert config.model == "yolo11n-seg.pt"
    assert config.epochs == 100
    assert config.imgsz == 640
    assert config.project == Path("cv/runs")
    assert config.device is None


def test_config_rejects_unknown_key() -> None:
    with pytest.raises(ValueError, match="unknown config keys: epocs"):
        train.parse_config({"epocs": 5})


def test_config_rejects_invalid_epochs() -> None:
    with pytest.raises(ValueError, match="epochs must be between"):
        train.parse_config({"epochs": 0})


def test_build_train_kwargs_maps_config(tmp_path: Path) -> None:
    config = train.TrainConfig(epochs=5, imgsz=320, batch=2, seed=7, project=tmp_path)

    kwargs = train.build_train_kwargs(config, tmp_path / "dataset.yaml")

    assert kwargs["data"] == str(tmp_path / "dataset.yaml")
    assert kwargs["epochs"] == 5
    assert kwargs["imgsz"] == 320
    assert kwargs["batch"] == 2
    assert kwargs["seed"] == 7
    assert kwargs["exist_ok"] is True
    assert kwargs["device"] is None


def test_build_train_kwargs_forwards_device(tmp_path: Path) -> None:
    config = train.TrainConfig(device="0")

    kwargs = train.build_train_kwargs(config, tmp_path / "dataset.yaml")

    assert kwargs["device"] == "0"


def test_render_metrics_table_marks_missing_values() -> None:
    table = train.render_metrics_table([train.MetricsRow("all", 0.5, None, 0.25, None)])

    assert "| all | 0.5000 | — | 0.2500 | — |" in table


def test_sha256_file_matches_known_hash(tmp_path: Path) -> None:
    path = tmp_path / "file.bin"
    path.write_bytes(b"abc")

    assert (
        train.sha256_file(path)
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_dry_run_prints_plan_and_creates_nothing(tmp_path: Path, capsys: Any) -> None:
    root = build_dataset(tmp_path)

    code = train.main(
        ["--data", str(root), "--dry-run", "--project", str(tmp_path / "runs"), "--name", "dry"]
    )

    output = capsys.readouterr().out
    assert code == 0
    assert "classes: 2 (dent, scratch)" in output
    assert "splits: train 4 images" in output
    assert "name=dry" in output
    assert "dry run: nothing trained" in output
    assert not (tmp_path / "runs").exists()


def test_main_returns_2_on_invalid_dataset(tmp_path: Path, capsys: Any) -> None:
    root = build_dataset(tmp_path)
    (root / "labels" / "train" / "ghost.txt").write_text(POLYGON, encoding="utf-8")

    code = train.main(["--data", str(root), "--dry-run"])

    assert code == 2
    assert "dataset is invalid" in capsys.readouterr().err


def test_run_training_writes_measured_metrics(tmp_path: Path) -> None:
    root = build_dataset(tmp_path)
    model = FakeModel()
    config = train.TrainConfig(
        epochs=3, imgsz=128, batch=2, project=tmp_path / "runs", name="smoke"
    )

    report = train.run_training(config, root, model_factory=lambda name: model)

    assert model.train_calls[0]["epochs"] == 3
    assert model.train_calls[0]["data"].endswith("dataset.yaml")
    assert model.val_calls == [{"data": str(root / "dataset.yaml"), "split": "val"}]
    assert report["split"] == "val"
    assert report["overall"]["map50"] == pytest.approx(0.65)
    assert report["weights"] is None

    run_dir = tmp_path / "runs" / "smoke"
    saved = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert [row["label"] for row in saved["classes"]] == ["dent", "scratch"]
    assert saved["overall"]["map50_95"] == pytest.approx(0.4)
    table = (run_dir / "metrics.md").read_text(encoding="utf-8")
    assert "| dent | 0.8000 | 0.7000 | 0.7500 | 0.5000 |" in table
    assert "test не использовался" in table


def test_run_training_uses_best_weights_and_checksum(tmp_path: Path) -> None:
    root = build_dataset(tmp_path)
    best = tmp_path / "best.pt"
    best.write_bytes(b"weights")
    last = FakeModel()
    last.trainer = FakeTrainer(best)
    loaded = FakeModel()

    def factory(name: str) -> FakeModel:
        return loaded if name == str(best) else last

    config = train.TrainConfig(epochs=1, imgsz=128, batch=1, project=tmp_path / "runs", name="best")

    report = train.run_training(config, root, model_factory=factory)

    assert last.train_calls
    assert loaded.val_calls
    assert report["weights"] == str(best)
    assert report["weights_sha256"] == hashlib.sha256(b"weights").hexdigest()
