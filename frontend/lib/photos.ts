const UPLOAD_MAX_SIDE = 1600;
const UPLOAD_QUALITY = 0.85;
const PREVIEW_MAX_SIDE = 720;
const PREVIEW_QUALITY = 0.72;

const READ_ERROR = "Не удалось прочитать фото. Попробуйте выбрать другой файл.";

export interface PreparedPhoto {
  blob: Blob;
  previewUrl: string;
  width: number;
  height: number;
}

interface DecodedPhoto {
  source: CanvasImageSource;
  width: number;
  height: number;
  release: () => void;
}

function fit(width: number, height: number, maxSide: number): { width: number; height: number } {
  const scale = Math.min(1, maxSide / Math.max(width, height));
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

function loadImage(file: File): Promise<DecodedPhoto> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve({
        source: image,
        width: image.naturalWidth,
        height: image.naturalHeight,
        release: () => {},
      });
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(READ_ERROR));
    };
    image.src = url;
  });
}

async function decode(file: File): Promise<DecodedPhoto> {
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
      return {
        source: bitmap,
        width: bitmap.width,
        height: bitmap.height,
        release: () => bitmap.close(),
      };
    } catch {
      // Часть мобильных браузеров не поддерживает опции createImageBitmap.
    }
  }
  return loadImage(file);
}

function render(source: CanvasImageSource, width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Браузер не поддерживает обработку фото.");
  }
  // Белая подложка: прозрачные PNG не должны стать чёрными после перекодирования в JPEG.
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);
  context.drawImage(source, 0, 0, width, height);
  return canvas;
}

function toBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("Не удалось сжать фото. Попробуйте ещё раз."));
        }
      },
      "image/jpeg",
      quality,
    );
  });
}

export async function preparePhoto(file: File): Promise<PreparedPhoto> {
  if (!file.type.startsWith("image/")) {
    throw new Error("Выберите файл изображения.");
  }

  const decoded = await decode(file);
  try {
    const uploadSize = fit(decoded.width, decoded.height, UPLOAD_MAX_SIDE);
    const uploadCanvas = render(decoded.source, uploadSize.width, uploadSize.height);
    const blob = await toBlob(uploadCanvas, UPLOAD_QUALITY);

    const previewSize = fit(uploadSize.width, uploadSize.height, PREVIEW_MAX_SIDE);
    const previewCanvas = render(uploadCanvas, previewSize.width, previewSize.height);

    return {
      blob,
      previewUrl: previewCanvas.toDataURL("image/jpeg", PREVIEW_QUALITY),
      width: uploadSize.width,
      height: uploadSize.height,
    };
  } finally {
    decoded.release();
  }
}
