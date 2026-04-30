import logging
import os

import cv2
import numpy as np

from config import PROCESSED_DIR

logger = logging.getLogger(__name__)

MAX_DIMENSION = 2000  # Resize images larger than this before processing


def _load_with_exif(image_path: str):
    """Load image and apply EXIF rotation so pixel orientation matches display orientation."""
    try:
        from PIL import Image as PILImage, ImageOps
        pil_img = PILImage.open(image_path)
        pil_img = ImageOps.exif_transpose(pil_img)  # rotate pixels to match EXIF orientation
        pil_img = pil_img.convert("RGB")
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except Exception:
        pass
    return cv2.imread(image_path)  # fallback: PNG/already-processed images have no EXIF


def _resize_if_needed(image: np.ndarray) -> np.ndarray:
    """Resize image so longest side <= MAX_DIMENSION."""
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= MAX_DIMENSION:
        return image
    scale = MAX_DIMENSION / longest
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def deskew(image: np.ndarray) -> np.ndarray:
    """Deskew image using contour-based angle estimation."""
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
        gray = cv2.bitwise_not(gray)
        coords = np.column_stack(np.where(gray > 0))
        if len(coords) < 50:
            return image
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 0.5 or abs(angle) > 45:
            return image
        (h, w) = image.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        return cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    except Exception as exc:
        logger.warning("deskew failed, skipping: %s", exc)
        return image


def denoise(image: np.ndarray) -> np.ndarray:
    """Denoise using a fast bilateral filter (faster + safer than NLM on large images)."""
    try:
        return cv2.bilateralFilter(image, 9, 75, 75)
    except Exception as exc:
        logger.warning("denoise failed, skipping: %s", exc)
        return image


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    """Apply CLAHE contrast enhancement."""
    try:
        if len(image.shape) == 3:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
        else:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            return clahe.apply(image)
    except Exception as exc:
        logger.warning("enhance_contrast failed, skipping: %s", exc)
        return image


def sharpen(image: np.ndarray) -> np.ndarray:
    """Sharpen using unsharp mask."""
    try:
        blurred = cv2.GaussianBlur(image, (0, 0), 3)
        return cv2.addWeighted(image, 1.5, blurred, -0.5, 0)
    except Exception as exc:
        logger.warning("sharpen failed, skipping: %s", exc)
        return image


def preprocess_pipeline(image_path: str) -> str:
    """
    Full preprocessing pipeline.
    Returns path to preprocessed image saved in PROCESSED_DIR.
    """
    image = _load_with_exif(image_path)
    if image is None:
        raise ValueError(f"Cannot load image {image_path}")

    image = _resize_if_needed(image)
    image = deskew(image)
    image = denoise(image)
    image = enhance_contrast(image)
    image = sharpen(image)

    basename = os.path.splitext(os.path.basename(image_path))[0]
    out_path = os.path.join(PROCESSED_DIR, f"{basename}_preprocessed.png")
    cv2.imwrite(out_path, image)
    logger.info("Preprocessed image saved: %s", out_path)
    return out_path
