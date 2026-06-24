import logging
import os
from pathlib import Path

import cv2
import numpy as np

from config import PROCESSED_DIR

logger = logging.getLogger(__name__)

MAX_DIMENSION = 2000  # Resize images larger than this before processing
PDF_RENDER_DPI = int(os.environ.get("PDF_RENDER_DPI", "200"))
PDF_RENDER_PAGE = int(os.environ.get("PDF_RENDER_PAGE", "1"))
MAX_PDF_PAGES = int(os.environ.get("MAX_PDF_PAGES", "50"))


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


OCR_SHARPEN_STRENGTH = max(0.0, min(_float_env("OCR_SHARPEN_STRENGTH", 0.0), 0.35))


def _processed_path(image_path: str, suffix: str) -> str:
    basename = os.path.splitext(os.path.basename(image_path))[0]
    return os.path.join(PROCESSED_DIR, f"{basename}_{suffix}.png")


def processed_display_path(image_path: str) -> str:
    """Path for the clean geometry-aligned image used for preview/export."""
    return _processed_path(image_path, "display")


def processed_ocr_path(image_path: str) -> str:
    """Path for the OCR-enhanced image used only by OCR."""
    return _processed_path(image_path, "preprocessed")


def _is_pdf(path: str) -> bool:
    return os.path.splitext(path)[1].lower() == ".pdf"


def _render_pdf_page(pdf_path: str):
    """Render a bounded PDF page to an OpenCV image."""
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise ValueError("PDF support requires pdf2image and Poppler.") from exc

    try:
        pages = convert_from_path(
            pdf_path,
            dpi=PDF_RENDER_DPI,
            first_page=PDF_RENDER_PAGE,
            last_page=PDF_RENDER_PAGE,
            fmt="png",
            thread_count=1,
        )
    except Exception as exc:
        raise ValueError("PDF could not be rendered. Check that the file is valid and Poppler is installed.") from exc

    if not pages:
        raise ValueError("PDF could not be rendered because the selected page was empty.")

    pil_img = pages[0].convert("RGB")
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def _pdf_page_count(pdf_path: str) -> int:
    try:
        from PyPDF2 import PdfReader
        return len(PdfReader(pdf_path).pages)
    except Exception as exc:
        raise ValueError("PDF page count could not be read. Check that the file is valid.") from exc


def _render_pdf_pages(pdf_path: str):
    """Render every PDF page up to MAX_PDF_PAGES."""
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise ValueError("PDF support requires pdf2image and Poppler.") from exc

    page_count = _pdf_page_count(pdf_path)
    if page_count > MAX_PDF_PAGES:
        raise ValueError(
            f"PDF has {page_count} pages. First iteration supports up to {MAX_PDF_PAGES}; split the PDF and upload again."
        )

    try:
        pages = convert_from_path(
            pdf_path,
            dpi=PDF_RENDER_DPI,
            first_page=1,
            last_page=page_count,
            fmt="png",
            thread_count=1,
        )
    except Exception as exc:
        raise ValueError("PDF could not be rendered. Check that the file is valid and Poppler is installed.") from exc

    if not pages:
        raise ValueError("PDF could not be rendered because it did not contain readable pages.")
    return [cv2.cvtColor(np.array(page.convert("RGB")), cv2.COLOR_RGB2BGR) for page in pages]


def _load_with_exif(image_path: str):
    """Load image and apply EXIF rotation so pixel orientation matches display orientation."""
    if _is_pdf(image_path):
        return _render_pdf_page(image_path)

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
    """Optionally apply a gentle unsharp mask for OCR only."""
    if OCR_SHARPEN_STRENGTH <= 0:
        return image
    try:
        blurred = cv2.GaussianBlur(image, (0, 0), 1.2)
        return cv2.addWeighted(
            image,
            1.0 + OCR_SHARPEN_STRENGTH,
            blurred,
            -OCR_SHARPEN_STRENGTH,
            0,
        )
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
        raise ValueError("Cannot load image. The file may be corrupt or unsupported.")

    image = _resize_if_needed(image)
    image = deskew(image)

    display_path = processed_display_path(image_path)
    cv2.imwrite(display_path, image)

    ocr_image = denoise(image.copy())
    ocr_image = enhance_contrast(ocr_image)
    ocr_image = sharpen(ocr_image)

    out_path = processed_ocr_path(image_path)
    cv2.imwrite(out_path, ocr_image)
    logger.info("Display image saved: %s", display_path)
    logger.info("Preprocessed image saved: %s", out_path)
    return out_path


def _write_page_derivatives(image: np.ndarray, out_dir: str, page_number: int) -> dict:
    """Write original/display/OCR images for one page and return page metadata."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    stem = f"page_{page_number:04d}"

    original_path = os.path.join(out_dir, f"{stem}_original.png")
    display_path = os.path.join(out_dir, f"{stem}_display.png")
    ocr_path = os.path.join(out_dir, f"{stem}_ocr.png")

    cv2.imwrite(original_path, image)

    display_image = _resize_if_needed(image)
    display_image = deskew(display_image)
    cv2.imwrite(display_path, display_image)

    ocr_image = denoise(display_image.copy())
    ocr_image = enhance_contrast(ocr_image)
    ocr_image = sharpen(ocr_image)
    cv2.imwrite(ocr_path, ocr_image)

    height, width = display_image.shape[:2]
    return {
        "page_number": page_number,
        "original_image_path": original_path,
        "display_image_path": display_path,
        "ocr_image_path": ocr_path,
        "width": width,
        "height": height,
    }


def render_document_pages(input_path: str, out_dir: str) -> list[dict]:
    """Render an image/PDF upload into per-page images for processing and review."""
    if _is_pdf(input_path):
        images = _render_pdf_pages(input_path)
    else:
        image = _load_with_exif(input_path)
        if image is None:
            raise ValueError("Cannot load image. The file may be corrupt or unsupported.")
        images = [image]

    return [
        _write_page_derivatives(image, out_dir, index + 1)
        for index, image in enumerate(images)
    ]
