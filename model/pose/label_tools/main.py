from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from PIL import Image
import json


ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
POINT_NAMES = [
    "upper_back_center",
    "trunk_mid",
    "pelvis_center",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_hand",
    "right_hand",
    "left_knee",
    "right_knee",
    "left_foot_center",
    "right_foot_center",
]
Visibility = Literal["visible", "occluded", "unreliable"]


class PointData(BaseModel):
    x: float | None = None
    y: float | None = None
    visibility: Visibility = "visible"


class LabelData(BaseModel):
    image: str
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    points: dict[str, PointData]


class SaveRequest(BaseModel):
    image_name: str
    output_dir: str
    data: LabelData


app = FastAPI(
    title="Pose Label Tool Backend",
    version="1.0.0",
    description="Local filesystem backend for pose image labeling.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_existing_dir(raw_path: str, *, field_name: str) -> Path:
    if not raw_path.strip():
        raise HTTPException(status_code=400, detail=f"{field_name} 不能为空")
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{field_name} 不存在: {path}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"{field_name} 不是目录: {path}")
    return path


def _resolve_output_dir(raw_path: str) -> Path:
    if not raw_path.strip():
        raise HTTPException(status_code=400, detail="output_dir 不能为空")
    path = Path(raw_path).expanduser().resolve()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法创建输出目录: {path} ({exc})") from exc
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"output_dir 不是目录: {path}")
    return path


def _validate_image_name(image_name: str) -> str:
    if not image_name.strip():
        raise HTTPException(status_code=400, detail="image_name 不能为空")
    name = Path(image_name).name
    if name != image_name:
        raise HTTPException(status_code=400, detail="image_name 不能包含路径")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"不支持的图片类型: {suffix or '(empty)'}")
    return name


def _label_path(output_dir: Path, image_name: str) -> Path:
    return output_dir / f"{Path(image_name).stem}.json"


def _image_path(input_dir: Path, image_name: str) -> Path:
    return input_dir / image_name


def _empty_label(image_name: str) -> dict[str, object]:
    return {
        "image": image_name,
        "width": 0,
        "height": 0,
        "points": {
            point_name: {"x": None, "y": None, "visibility": "visible"}
            for point_name in POINT_NAMES
        },
    }


def _normalize_label_payload(data: LabelData, *, image_name: str) -> dict[str, object]:
    points: dict[str, dict[str, object]] = {
        point_name: {"x": None, "y": None, "visibility": "visible"}
        for point_name in POINT_NAMES
    }

    for point_name, point_value in data.points.items():
        if point_name not in POINT_NAMES:
            continue
        points[point_name] = point_value.model_dump()

    return {
        "image": image_name,
        "width": int(data.width),
        "height": int(data.height),
        "points": points,
    }


@app.get("/api/images")
def list_images(input_dir: str = Query(..., description="图片文件夹路径")) -> dict[str, object]:
    image_dir = _resolve_existing_dir(input_dir, field_name="input_dir")

    images: list[dict[str, object]] = []
    for image_path in sorted(image_dir.iterdir(), key=lambda p: p.name.lower()):
        if not image_path.is_file():
            continue
        if image_path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
            continue

        try:
            with Image.open(image_path) as img:
                width, height = img.size
        except OSError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"无法读取图片尺寸: {image_path.name} ({exc})",
            ) from exc

        images.append(
            {
                "file_name": image_path.name,
                "width": int(width),
                "height": int(height),
            }
        )

    return {"images": images}


@app.get("/api/label")
def get_label(
    image_name: str = Query(..., description="图片文件名"),
    output_dir: str = Query(..., description="标注输出目录"),
) -> dict[str, object]:
    safe_image_name = _validate_image_name(image_name)
    label_file = _label_path(_resolve_output_dir(output_dir), safe_image_name)

    if not label_file.exists():
        return _empty_label(safe_image_name)

    try:
        with label_file.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        parsed = LabelData.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"标注文件格式错误: {label_file} ({exc})",
        ) from exc

    return _normalize_label_payload(parsed, image_name=safe_image_name)


@app.get("/api/image-file")
def get_image_file(
    input_dir: str = Query(..., description="图片目录"),
    image_name: str = Query(..., description="图片文件名"),
) -> FileResponse:
    safe_image_name = _validate_image_name(image_name)
    image_file = _image_path(_resolve_existing_dir(input_dir, field_name="input_dir"), safe_image_name)
    if not image_file.exists() or not image_file.is_file():
        raise HTTPException(status_code=404, detail=f"图片不存在: {image_file}")
    return FileResponse(path=image_file)


@app.post("/api/save")
def save_label(req: SaveRequest) -> dict[str, object]:
    safe_image_name = _validate_image_name(req.image_name)
    output_dir = _resolve_output_dir(req.output_dir)
    label_file = _label_path(output_dir, safe_image_name)

    payload = _normalize_label_payload(req.data, image_name=safe_image_name)

    try:
        with label_file.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"保存标注失败: {label_file} ({exc})",
        ) from exc

    return {
        "ok": True,
        "file": str(label_file),
        "image_name": safe_image_name,
    }


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=9001, reload=True)
