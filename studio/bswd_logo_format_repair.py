#!/usr/bin/env python3
"""Repair the BSWD logo's mislabeled container without changing its artwork.

The repository path ends in .png but the source bytes are JPEG. This guarded
repair decodes the existing JPEG once, writes the identical decoded RGB pixels
into a true PNG container, preserves the ICC profile, then adds truthful
BSWD/Lace & Leather Arcane Studio metadata. Existing third-party provenance,
rights, unusual orientation, or authenticity credentials stop the repair.
"""
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = Path("stag-studio/bsw-logo.png")
TARGET = ROOT / RELATIVE
REPORT = ROOT / "studio/bswd-logo-format-repair.json"

STUDIO = "Lace & Leather Arcane Studio"
OWNER = "Black Stag Web Design"
RIGHTS = "Copyright 2026 Black Stag Web Design"
WEB = "https://blackstagweb.com/ownership.html"
DESCRIPTION = "Black Stag Web Design logo artwork; produced and prepared by Lace & Leather Arcane Studio."

CREDENTIAL_MARKERS = (
    b"c2pa", b"jumbf", b"content credentials", b"contentcredentials",
)
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
        raise RuntimeError("ExifTool returned an unexpected record count")
    return rows[0]


def has_authenticity_credentials(raw: bytes, metadata: dict) -> bool:
    lower = raw.lower()
    if any(marker in lower for marker in CREDENTIAL_MARKERS):
        return True
    return any(
        "c2pa" in key.lower()
        or "jumbf" in key.lower()
        or "contentcredentials" in key.lower()
        for key in metadata
    )


def conflicting_rights(metadata: dict) -> list[str]:
    allowed = (STUDIO.lower(), OWNER.lower())
    bad = []
    for field in CREDIT_FIELDS:
        value = metadata.get(field)
        if value in (None, ""):
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        if not any(token in str(value).lower() for token in allowed):
            bad.append(field)
    for field in DANGEROUS_RIGHTS_FIELDS:
        if metadata.get(field):
            bad.append(field)
    return sorted(set(bad))


def image_state(path: Path) -> dict:
    with Image.open(path) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise RuntimeError("Animated or multiframe image is out of scope")
        image.load()
        rgb = image.convert("RGB")
        icc = image.info.get("icc_profile") or b""
        if not isinstance(icc, bytes):
            icc = str(icc).encode("utf-8")
        return {
            "format": image.format,
            "size": list(image.size),
            "mode": image.mode,
            "rgb_pixel_sha256": digest(rgb.tobytes()),
            "icc_sha256": digest(icc),
            "icc_bytes": icc,
        }


def required_metadata() -> dict:
    return {
        "XMP-dc:Creator": STUDIO,
        "XMP-dc:Rights": RIGHTS,
        "XMP-dc:Description": DESCRIPTION,
        "XMP-dc:Source": STUDIO,
        "XMP-photoshop:Credit": STUDIO + " (artwork production and preparation)",
        "XMP-xmpRights:WebStatement": WEB,
    }


def metadata_matches(metadata: dict) -> bool:
    for key, expected in required_metadata().items():
        actual = metadata.get(key)
        if isinstance(actual, list):
            actual = ", ".join(str(item) for item in actual)
        if str(actual or "") != expected:
            return False
    return True


def main() -> None:
    if not TARGET.is_file():
        raise RuntimeError(f"Missing target: {RELATIVE}")

    original = TARGET.read_bytes()
    original_sha = digest(original)
    if not original.startswith(b"\xff\xd8"):
        raise RuntimeError("Guard stopped: target is no longer JPEG bytes")

    before_meta = exiftool_metadata(TARGET)
    if has_authenticity_credentials(original, before_meta):
        raise RuntimeError("Guard stopped: source carries authenticity credentials")

    conflicts = conflicting_rights(before_meta)
    if conflicts:
        raise RuntimeError("Guard stopped: conflicting creator/rights metadata: " + ", ".join(conflicts))

    orientation = before_meta.get("EXIF:Orientation")
    if orientation not in (None, "", 1, "1", "Horizontal (normal)"):
        raise RuntimeError(f"Guard stopped: non-normal EXIF orientation: {orientation}")

    before = image_state(TARGET)
    if before["format"] != "JPEG":
        raise RuntimeError(f"Guard stopped: expected JPEG source, found {before['format']}")

    with Image.open(TARGET) as source:
        source.load()
        rgb = source.convert("RGB")
        save_args = {"format": "PNG", "optimize": False, "compress_level": 6}
        icc = source.info.get("icc_profile")
        if icc:
            save_args["icc_profile"] = icc
        temp = TARGET.with_name(TARGET.name + ".repair-temp")
        rgb.save(temp, **save_args)

    command = ["exiftool", "-overwrite_original", "-P"]
    command += [f"-{key}={value}" for key, value in required_metadata().items()]
    command.append(str(temp))
    write = subprocess.run(command, capture_output=True, text=True)
    if write.returncode != 0 or "1 image files updated" not in write.stdout:
        temp.unlink(missing_ok=True)
        raise RuntimeError("ExifTool refused or failed metadata write")

    repaired = temp.read_bytes()
    if not repaired.startswith(b"\x89PNG\r\n\x1a\n"):
        temp.unlink(missing_ok=True)
        raise RuntimeError("Repair output is not a true PNG")

    after = image_state(temp)
    after_meta = exiftool_metadata(temp)
    if after["format"] != "PNG":
        temp.unlink(missing_ok=True)
        raise RuntimeError("Pillow does not recognize repair output as PNG")
    if before["size"] != after["size"]:
        temp.unlink(missing_ok=True)
        raise RuntimeError("Dimensions changed during repair")
    if before["rgb_pixel_sha256"] != after["rgb_pixel_sha256"]:
        temp.unlink(missing_ok=True)
        raise RuntimeError("Decoded RGB pixels changed during repair")
    if before["icc_sha256"] != after["icc_sha256"]:
        temp.unlink(missing_ok=True)
        raise RuntimeError("ICC profile changed during repair")
    if has_authenticity_credentials(repaired, after_meta):
        temp.unlink(missing_ok=True)
        raise RuntimeError("Unexpected authenticity marker after repair")
    if not metadata_matches(after_meta):
        temp.unlink(missing_ok=True)
        raise RuntimeError("Required studio/rights metadata failed readback")

    temp.replace(TARGET)

    report = {
        "schema_version": 1,
        "path": RELATIVE.as_posix(),
        "project_owner": OWNER,
        "production_studio": STUDIO,
        "source_sha256": original_sha,
        "output_sha256": digest(TARGET.read_bytes()),
        "source_container_format": "JPEG",
        "output_container_format": "PNG",
        "dimensions": before["size"],
        "decoded_rgb_pixels_unchanged": True,
        "icc_profile_unchanged": True,
        "source_authenticity_credentials": False,
        "conflicting_source_rights": [],
        "metadata": required_metadata(),
        "visual_review": "pending",
        "live_site_code_changed": False,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
