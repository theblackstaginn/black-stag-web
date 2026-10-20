#!/usr/bin/env python3
"""Guarded metadata-only retrofit for BSWD client portfolio presentation images.

Each image keeps the client/project as rights holder while Lace & Leather Arcane
Studio receives production/origin credit. Existing conflicting rights,
authenticity credentials, unreadable/mismatched formats, animation, or any
pixel/payload change causes a hold or abort.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STUDIO = "Lace & Leather Arcane Studio"
BSWD = "Black Stag Web Design"
RIGHTS_URL = "https://blackstagweb.com/ownership.html"
SUPPORTED = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}
CONTENT = {
    ".png": {"IDAT", "PLTE", "tRNS", "acTL", "fcTL", "fdAT"},
    ".webp": {"VP8 ", "VP8L", "ALPH", "ANIM", "ANMF"},
}
MARKERS = (b"c2pa", b"jumbf", b"content credentials", b"contentcredentials")
CREDIT_FIELDS = (
    "XMP-dc:Creator", "EXIF:Artist", "IPTC:By-line",
    "XMP-dc:Rights", "EXIF:Copyright", "IPTC:CopyrightNotice",
    "XMP-xmpRights:Owner", "XMP-photoshop:Credit",
)
DANGEROUS_RIGHTS_FIELDS = (
    "XMP-xmpRights:UsageTerms", "XMP-plus:LicensorName",
    "XMP-iptcExt:DigitalSourceType",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def image_state(path: Path) -> dict:
    with Image.open(path) as image:
        frames = getattr(image, "n_frames", 1)
        if frames != 1:
            raise RuntimeError("animated_or_multiframe")
        image.load()
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        icc = image.info.get("icc_profile") or b""
        if not isinstance(icc, bytes):
            icc = str(icc).encode("utf-8")
        return {
            "format": image.format,
            "size": list(image.size),
            "frames": frames,
            "pixel_sha256": digest(rgba.tobytes()),
            "alpha_sha256": digest(alpha.tobytes()),
            "icc_sha256": digest(icc),
        }


def picture_hash(data: bytes, suffix: str) -> str:
    parts = []
    if suffix == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("not_png")
        cursor = 8
        while cursor + 12 <= len(data):
            count = int.from_bytes(data[cursor:cursor + 4], "big")
            tag = data[cursor + 4:cursor + 8].decode("ascii")
            end = cursor + count + 12
            if end > len(data):
                raise ValueError("truncated_png")
            if tag in CONTENT[suffix]:
                parts.append(data[cursor + 4:cursor + 8 + count])
            cursor = end
            if tag == "IEND":
                break
    elif suffix == ".webp":
        if not (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
            raise ValueError("not_webp")
        cursor = 12
        while cursor + 8 <= len(data):
            count = int.from_bytes(data[cursor + 4:cursor + 8], "little")
            tag = data[cursor:cursor + 4].decode("ascii")
            end = cursor + 8 + count
            if end > len(data):
                raise ValueError("truncated_webp")
            if tag in CONTENT[suffix]:
                parts.append(data[cursor:end])
            cursor = end + (count % 2)
    elif suffix in {".jpg", ".jpeg"}:
        if not data.startswith(b"\xff\xd8"):
            raise ValueError("not_jpeg")
        cursor = 2
        while cursor < len(data) - 4:
            if data[cursor] != 0xff:
                raise ValueError("unexpected_jpeg_segment")
            while data[cursor] == 0xff:
                cursor += 1
            marker = data[cursor]
            cursor += 1
            if marker in (0xd8, 0xd9, 0x01) or 0xd0 <= marker <= 0xd7:
                continue
            segment_length = int.from_bytes(data[cursor:cursor + 2], "big")
            if segment_length < 2:
                raise ValueError("malformed_jpeg")
            if marker == 0xda:
                parts.append(data[cursor + segment_length:])
                break
            cursor += segment_length
    if not parts:
        raise RuntimeError("no_picture_payload")
    return digest(b"".join(parts))


def metadata(path: Path) -> dict:
    result = subprocess.run(
        ["exiftool", "-j", "-G1", "-a", "-s", str(path)],
        capture_output=True, text=True, check=True,
    )
    rows = json.loads(result.stdout)
    if len(rows) != 1:
        raise RuntimeError("unexpected_exiftool_record_count")
    return rows[0]


def protected(raw: bytes, meta: dict) -> bool:
    lower = raw.lower()
    if any(marker in lower for marker in MARKERS):
        return True
    return any(
        "c2pa" in key.lower()
        or "jumbf" in key.lower()
        or "contentcredentials" in key.lower()
        for key in meta
    )


def conflicts(meta: dict, project: str) -> list[str]:
    allowed = (STUDIO.lower(), BSWD.lower(), project.lower())
    bad = []
    for field in CREDIT_FIELDS:
        value = meta.get(field)
        if value in (None, ""):
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        low = str(value).lower()
        if not any(token in low for token in allowed):
            bad.append(field)
    for field in DANGEROUS_RIGHTS_FIELDS:
        if meta.get(field):
            bad.append(field)
    return sorted(set(bad))


def required(entry: dict) -> dict:
    return {
        "XMP-dc:Creator": STUDIO,
        "XMP-dc:Rights": entry["rights"],
        "XMP-dc:Description": entry["description"],
        "XMP-dc:Source": STUDIO,
        "XMP-photoshop:Credit": STUDIO + " (portfolio image production and preparation)",
        "XMP-xmpRights:WebStatement": RIGHTS_URL,
    }


def matches(meta: dict, entry: dict) -> bool:
    for key, expected in required(entry).items():
        actual = meta.get(key)
        if isinstance(actual, list):
            actual = ", ".join(str(item) for item in actual)
        if str(actual or "") != expected:
            return False
    return True


def process(entry: dict) -> dict:
    rel = Path(entry["path"])
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe_path:{rel}")
    suffix = rel.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"unsupported_extension:{rel}")
    path = (ROOT / rel).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError(f"missing_path:{rel}")
    if not rel.as_posix().startswith("stag-studio/"):
        raise ValueError(f"outside_portfolio_scope:{rel}")

    raw = path.read_bytes()
    source_sha = digest(raw)
    record = {
        "path": rel.as_posix(),
        "project": entry["project"],
        "website": entry["website"],
        "rights": entry["rights"],
        "source_sha256": source_sha,
    }
    if len(raw) > 15_000_000:
        record.update(
            status="held_for_review",
            reason="file_exceeds_batch_limit",
            output_sha256=source_sha,
        )
        return record

    try:
        before = image_state(path)
        payload = picture_hash(raw, suffix)
        before_meta = metadata(path)
    except Exception as exc:
        record.update(
            status="held_for_review",
            reason="unsupported_or_unreadable_image",
            detail=type(exc).__name__,
            output_sha256=source_sha,
        )
        return record

    if before["format"] != SUPPORTED[suffix]:
        record.update(
            status="held_for_review",
            reason="file_extension_format_mismatch",
            detected_format=before["format"],
            output_sha256=source_sha,
        )
        return record

    record.update(
        format=before["format"],
        dimensions=before["size"],
        pixel_sha256=before["pixel_sha256"],
        encoded_picture_sha256=payload,
    )

    if protected(raw, before_meta):
        record.update(
            status="held_for_review",
            reason="existing_authenticity_credentials",
            output_sha256=source_sha,
        )
        return record

    bad = conflicts(before_meta, entry["project"])
    if bad:
        record.update(
            status="held_for_review",
            reason="conflicting_creator_or_rights",
            conflicting_fields=bad,
            output_sha256=source_sha,
        )
        return record

    if matches(before_meta, entry):
        record.update(status="already_credited", output_sha256=source_sha)
        return record

    command = ["exiftool", "-overwrite_original", "-P"]
    command += [f"-{key}={value}" for key, value in required(entry).items()]
    command.append(str(path))

    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0 or "1 image files updated" not in result.stdout:
            raise RuntimeError("metadata_write_failed")
        updated = path.read_bytes()
        after = image_state(path)
        after_payload = picture_hash(updated, suffix)
        after_meta = metadata(path)
        if before != after or payload != after_payload:
            raise RuntimeError("image_content_changed")
        if protected(updated, after_meta):
            raise RuntimeError("unexpected_authenticity_marker")
        if not matches(after_meta, entry):
            raise RuntimeError("metadata_readback_failed")
    except Exception:
        path.write_bytes(raw)
        raise

    record.update(
        status="verified_metadata_only",
        output_sha256=digest(updated),
        pixels_alpha_frames_profile_unchanged=True,
        compressed_picture_data_unchanged=True,
        creator=STUDIO,
        studio_credit=STUDIO + " (portfolio image production and preparation)",
        rights_statement_url=RIGHTS_URL,
    )
    return record


def run(manifest_path: Path, report_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("production_studio") != STUDIO:
        raise ValueError("unexpected_production_studio")
    entries = manifest.get("files") or []
    if len(entries) != 12 or len({entry["path"] for entry in entries}) != 12:
        raise ValueError("batch01_requires_12_unique_files")

    rows = []
    for entry in entries:
        result = process(entry)
        rows.append(result)
        print(result["status"], result["path"], flush=True)

    verified = [row for row in rows if row["status"] == "verified_metadata_only"]
    held = [row for row in rows if row["status"] == "held_for_review"]
    already = [row for row in rows if row["status"] == "already_credited"]
    if not verified and not already:
        raise RuntimeError("nothing_safely_processable")

    report = {
        "schema_version": 1,
        "batch": manifest["batch"],
        "production_studio": STUDIO,
        "total": len(rows),
        "verified_metadata_only": len(verified),
        "already_credited": len(already),
        "held_for_review": len(held),
        "updated_paths": [row["path"] for row in verified],
        "held_paths": [
            {"path": row["path"], "reason": row["reason"]} for row in held
        ],
        "visual_review": "pending",
        "live_site_code_changed": False,
        "files": rows,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="studio/bswd-client-portfolio-batch01.json")
    parser.add_argument("--report", default="studio/bswd-client-portfolio-batch01-results.json")
    args = parser.parse_args()
    run(ROOT / args.manifest, ROOT / args.report)
