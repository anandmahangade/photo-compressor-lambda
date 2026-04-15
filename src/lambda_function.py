"""
Lambda Function: Photo Compressor
----------------------------------
Trigger  : S3 PutObject on bucket "my-raw-photos"
Flow     : Fetch photo from S3  →  Compress with Pillow  →  Upload to "my-compressed-photos"  →  Notify via SNS
Runtime  : Python 3.12
Layer    : Pillow (add ARN from Klayers — see README below)
"""

import boto3
import io
import os
import json
import logging

from PIL import Image

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Configuration (set these as Lambda environment variables) ──────────────────
RAW_BUCKET       = os.environ.get("RAW_BUCKET",        "my-raw-photos")
COMPRESSED_BUCKET= os.environ.get("COMPRESSED_BUCKET", "my-compressed-photos")
SNS_TOPIC_ARN    = os.environ.get("SNS_TOPIC_ARN",     "arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:photo-compress-topic")

# Compression settings (tune to balance quality vs size)
JPEG_QUALITY     = int(os.environ.get("JPEG_QUALITY",  "60"))   # 1-95, lower = smaller file
MAX_WIDTH        = int(os.environ.get("MAX_WIDTH",     "1920"))  # resize if wider than this
MAX_HEIGHT       = int(os.environ.get("MAX_HEIGHT",    "1080"))  # resize if taller than this

# ── AWS clients ────────────────────────────────────────────────────────────────
s3  = boto3.client("s3")
sns = boto3.client("sns")


def lambda_handler(event, context):
    """
    Entry point. AWS calls this for each S3 PutObject event.
    One event can contain multiple records (batch), so we loop.
    """
    results = []

    for record in event["Records"]:
        result = process_record(record)
        results.append(result)

    return {
        "statusCode": 200,
        "body": json.dumps(results)
    }


def process_record(record):
    """
    Handles one S3 record: fetch → compress → upload → notify.
    Returns a summary dict.
    """
    bucket = record["s3"]["bucket"]["name"]
    key    = record["s3"]["object"]["key"]
    orig_size_bytes = record["s3"]["object"].get("size", 0)

    logger.info(f"Processing s3://{bucket}/{key}  ({orig_size_bytes} bytes)")

    # ── 1. Fetch original photo from S3 ───────────────────────────────────────
    response = s3.get_object(Bucket=bucket, Key=key)
    image_bytes = response["Body"].read()
    content_type = response.get("ContentType", "image/jpeg")

    # ── 2. Compress with Pillow ────────────────────────────────────────────────
    compressed_bytes, out_format = compress_image(image_bytes, key)
    compressed_size = len(compressed_bytes)

    savings_pct = round((1 - compressed_size / orig_size_bytes) * 100, 1) if orig_size_bytes else 0
    logger.info(f"Compressed {orig_size_bytes} → {compressed_size} bytes  ({savings_pct}% saved)")

    # ── 3. Upload compressed photo to output bucket ───────────────────────────
    output_key = build_output_key(key, out_format)
    s3.put_object(
    Bucket=COMPRESSED_BUCKET,
    Key=output_key,
    Body=compressed_bytes,
    ContentType=f"image/{out_format.lower()}",
    CacheControl="max-age=86400",
   )
    logger.info(f"Uploaded compressed photo to s3://{COMPRESSED_BUCKET}/{output_key}")

    # ── 4. Notify via SNS ─────────────────────────────────────────────────────
    notify_sns(
        original_key=key,
        output_key=output_key,
        original_size=orig_size_bytes,
        compressed_size=compressed_size,
        savings_pct=savings_pct,
        compressed_bucket=COMPRESSED_BUCKET
    )

    return {
        "original":  f"s3://{bucket}/{key}",
        "compressed": f"s3://{COMPRESSED_BUCKET}/{output_key}",
        "original_size_bytes":   orig_size_bytes,
        "compressed_size_bytes": compressed_size,
        "savings_percent":       savings_pct
    }


def compress_image(image_bytes: bytes, original_key: str):
    """
    Opens the image with Pillow, resizes if over MAX_WIDTH/MAX_HEIGHT,
    then saves as JPEG at JPEG_QUALITY.

    PNG files with transparency are kept as PNG (lossless compression).
    Everything else becomes JPEG.

    Returns: (compressed_bytes, format_string)
    """
    img = Image.open(io.BytesIO(image_bytes))

    # Convert palette/P-mode to RGBA or RGB so we can process properly
    if img.mode in ("P", "CMYK"):
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")

    # Determine output format: keep PNG if it has transparency
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    out_format = "PNG" if has_alpha else "JPEG"

    # Strip EXIF data (privacy + reduces file size)
    if hasattr(img, "_getexif"):  # JPEG only
        img = strip_exif(img)

    # Resize down if larger than max dimensions (maintain aspect ratio)
    original_size = img.size
    img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.LANCZOS)
    if img.size != original_size:
        logger.info(f"Resized {original_size} → {img.size}")

    # Save to in-memory buffer
    buffer = io.BytesIO()
    if out_format == "JPEG":
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(
            buffer,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,       # Huffman table optimization (smaller file)
            progressive=True     # Progressive JPEG (loads gradually in browser)
        )
    else:
        img.save(
            buffer,
            format="PNG",
            optimize=True,
            compress_level=7     # 0-9, higher = smaller but slower
        )

    buffer.seek(0)
    return buffer.read(), out_format


def strip_exif(img: Image.Image) -> Image.Image:
    """Returns a new PIL image without EXIF metadata."""
    clean = Image.new(img.mode, img.size)
    clean.putdata(list(img.getdata()))
    return clean


def build_output_key(original_key: str, out_format: str) -> str:
    """
    Maps  original/path/photo.jpg  →  original/path/photo_compressed.jpg
    Preserves folder structure.
    """
    name, _ = original_key.rsplit(".", 1) if "." in original_key else (original_key, "")
    extension = "jpg" if out_format == "JPEG" else "png"
    return f"{name}_compressed.{extension}"


def notify_sns(
    original_key: str,
    output_key: str,
    original_size: int,
    compressed_size: int,
    savings_pct: float,
    compressed_bucket: str
):
    """
    Publishes a structured JSON message to the SNS topic.
    Subscribers (email, HTTP webhook) receive this payload.
    """
    message_body = {
        "status":            "SUCCESS",
        "original_file":     original_key,
        "compressed_file":   output_key,
        "compressed_bucket": compressed_bucket,
        "original_size_kb":  round(original_size  / 1024, 2),
        "compressed_size_kb":round(compressed_size / 1024, 2),
        "savings_percent":   savings_pct,
        "access_url":        f"https://{compressed_bucket}.s3.amazonaws.com/{output_key}"
    }

    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=f"✅ Photo compressed — {savings_pct}% smaller",
        Message=json.dumps(message_body, indent=2),
        MessageAttributes={
            "event_type": {
                "DataType":    "String",
                "StringValue": "photo.compressed"
            }
        }
    )
    logger.info(f"SNS notification sent: {savings_pct}% savings")