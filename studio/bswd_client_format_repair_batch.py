#!/usr/bin/env python3
"""Guarded batch repair for client portfolio images mislabeled as PNG.

Each target path currently ends in .png but contains JPEG bytes. The repair
decodes the existing JPEG once, writes the identical RGB pixels into a true PNG
container at the same path, preserves ICC data, then adds truthful metadata.
Any authenticity credential, conflicting rights, non-normal orientation, or
pixel/profile mismatch stops that file from being changed.
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
MARKERS = (b"c2pa", b"jumbf", b"content credentials", b"contentcredentials")
CREDIT_FIELDS = (
    "XMP-dc:Creator", "EXIF:Artist", "IPTC:By-line",
    "XMP-dc:Rights", "EXIF:Copyright", "IPTC:CopyrightNotice",
    "XMP-xmpRights:Owner", "XMP-photoshop:Credit",
)
DANGEROUS_RIGHTS_FIELDS = (
    "XMP-xmpRights:UsageTerms",
    "XMP-plus:LicensorName",
    "XMP-iptcExt:DigitalSourceType",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exiftool_metadata(path: Path) -> dict:
    result = subprocess.run(
        ["exiftool", "-j", "-G1", "-a", "-s", str(path)],
        capture_output=True, text=True, check=True,
    )
    rows = json.loads(result.stdout)
    if len(rows) != 1:
        raise RuntimeError("unexpected_exiftool_record_count")
    return rows[0]


def has_authenticity_credentials(raw: bytes, metadata: dict) -> bool:
    lower = raw.lower()
    if any(marker in lower for marker in MARKERS):
        return True
    return any(
        "c2pa" in key.lower()
        or "jumbf" in key.lower()
        or "contentcredentials" in key.lower()
        for key in metadata
    )


def conflicting_rights(metadata: dict, project: str) -> list[str]:
    allowed = (STUDIO.lower(), BSWD.lower(), project.lower())
    bad = []
    for field in CREDIT_FIELDS:
        value = metadata.get(field)
        if value in (None, ""):
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        low = str(value).lower()
        if not any(token in low for token in allowed):
            bad.append(field)
    for field in DANGEROUS_RIGHTS_FIELDS:
        if metadata.get(field):
            bad.append(field)
    return sorted(set(bad))


def image_state(path: Path) -> dict:
    with Image.open(path) as image:
        frames = getattr(image, "n_frames", 1)
        if frames != 1:
            raise RuntimeError("animated_or_multiframe")
        image.load()
        rgb = image.convert("RGB")
        icc = image.info.get("icc_profile") or b""
        if not isinstance(icc, bytes):
            icc = str(icc).encode("utf-8")
        return {
            "format": image.format,
            "size": list(image.size),
            "frames": frames,
            "rgb_pixel_sha256": digest(rgb.tobytes()),
            "icc_sha256": digest(icc),
        }


def required(entry: dict) -> dict:
    return {
        "XMP-dc:Creator": STUDIO,
        "XMP-dc:Rights": entry["rights"],
        "XMP-dc:Description": entry["description"],
        "XMP-dc:Source": STUDIO,
        "XMP-photoshop:Credit": STUDIO + " (portfolio image production and preparation)",
        "XMP-xmpRights:WebStatement": RIGHTS_URL,
    }


def metadata_matches(meta: dict, entry: dict) -> bool:
    for key, expected in required(entry).items():
        actual = meta.get(key)
        if isinstance(actual, list):
            actual = ", ".join(str(item) for item in actual)
        if str(actual or "") != expected:
            return False
    return True


def repair_one(entry: dict) -> dict:
    rel = Path(entry["path"])
    if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() != ".png":
        raise ValueError(f"unsafe_target:{rel}")
    path = (ROOT / rel).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError(f"missing_target:{rel}")
    if not rel.as_posix().startswith("stag-studio/"):
        raise ValueError(f"outside_portfolio_scope:{rel}")

    original = path.read_bytes()
    source_sha = digest(original)
    record = {
        "path": rel.as_posix(),
        "project": entry["project"],
        "website": entry["website"],
        "rights": entry["rights"],
        "source_sha256": source_sha,
    }

    if not original.startswith(b"\xff\xd8"):
        record.update(
            status="held_for_review",
            reason="source_no_longer_jpeg_bytes",
            output_sha256=source_sha,
        )
        return record

    try:
        before_meta = exiftool_metadata(path)
        before = image_state(path)
    except Exception as exc:
        record.update(
            status="held_for_review",
            reason="source_unreadable",
            detail=type(exc).__name__,
            output_sha256=source_sha,
        )
        return record

    if before["format"] != "JPEG":
        record.update(
            status="held_for_review",
            reason="detected_format_not_jpeg",
            detected_format=before["format"],
            output_sha256=source_sha,
        )
        return record

    if has_authenticity_credentials(original, before_meta):
        record.update(
            status="held_for_review",
            reason="existing_authenticity_credentials",
            output_sha256=source_sha,
        )
        return record

    bad = conflicting_rights(before_meta, entry["project"])
    if bad:
        record.update(
            status="held_for_review",
            reason="conflicting_creator_or_rights",
            conflicting_fields=bad,
            output_sha256=source_sha,
        )
        return record

    orientation = before_meta.get("EXIF:Orientation")
    if orientation not in (None, "", 1, "1", "Horizontal (normal)"):
        record.update(
            status="held_for_review",
            reason="non_normal_exif_orientation",
            orientation=orientation,
            output_sha256=source_sha,
        )
        return record

    temp = path.with_name(path.name + ".repair-temp")
    try:
        with Image.open(path) as source:
            source.load()
            rgb = source.convert("RGB")
            save_args = {"format": "PNG", "optimize": False, "compress_level": 6}
            icc = source.info.get("icc_profile")
            if icc:
                save_args["icc_profile"] = icc
            rgb.save(temp, **save_args)

        command = ["exiftool", "-overwrite_original", "-P"]
        command += [f"-{key}={value}" for key, value in required(entry).items()]
        command.append(str(temp))
        write = subprocess.run(command, capture_output=True, text=True)
        if write.returncode != 0 or "1 image files updated" not in write.stdout:
            raise RuntimeError("metadata_write_failed")

        repaired = temp.read_bytes()
        if not repaired.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("repair_output_not_png")

        after = image_state(temp)
        after_meta = exiftool_metadata(temp)
        if after["format"] != "PNG":
            raise RuntimeError("repair_output_not_recognized_as_png")
        if before["size"] != after["size"]:
            raise RuntimeError("dimensions_changed")
        if before["rgb_pixel_sha256"] != after["rgb_pixel_sha256"]:
            raise RuntimeError("decoded_rgb_pixels_changed")
        if before["icc_sha256"] != after["icc_sha256"]:
            raise RuntimeError("icc_profile_changed")
        if has_authenticity_credentials(repaired, after_meta):
            raise RuntimeError("unexpected_authenticity_marker")
        if not metadata_matches(after_meta, entry):
            raise RuntimeError("metadata_readback_failed")

        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True)
        path.write_bytes(original)
        raise

    record.update(
        status="verified_format_repair",
        output_sha256=digest(path.read_bytes()),
        source_container_format="JPEG",
        output_container_format="PNG",
        dimensions=before["size"],
        decoded_rgb_pixels_unchanged=True,
        icc_profile_unchanged=True,
        source_authenticity_credentials=False,
        conflicting_source_rights=[],
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
    if len(entries) != 5 or len({entry["path"] for entry in entries}) != 5:
        raise ValueError("repair_batch_requires_five_unique_files")

    rows = []
    for entry in entries:
        result = repair_one(entry)
        rows.append(result)
        print(result["status"], result["path"], flush=True)

    verified = [row for row in rows if row["status"] == "verified_format_repair"]
    held = [row for row in rows if row["status"] == "held_for_review"]
    if not verified:
        raise RuntimeError("no_safe_repairs_completed")

    report = {
        "schema_version": 1,
        "batch": manifest["batch"],
        "production_studio": STUDIO,
        "total": len(rows),
        "verified_format_repairs": len(verified),
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
    parser.add_argument("--manifest", default="studio/bswd-client-format-repair-batch01.json")
    parser.add_argument("--report", default="studio/bswd-client-format-repair-batch01-results.json")
    args = parser.parse_args()
    run(ROOT / args.manifest, ROOT / args.report)
