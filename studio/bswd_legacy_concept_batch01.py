#!/usr/bin/env python3
"""Guarded retrofit for legacy Black Stag Web Design concept portfolio images.

Historical Black Stag portfolio copy explicitly classifies these five projects
as concept demos. This batch keeps Black Stag Web Design as rights holder for
the presentation artwork and records Lace & Leather Arcane Studio as the
production/origin studio.

True PNGs receive metadata-only edits. A .png path containing JPEG bytes is
repaired into a true PNG at the same path while preserving decoded RGB pixels
and ICC profile. Existing authenticity credentials, conflicting rights,
animation, unusual orientation, or any integrity mismatch stop the write.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
STUDIO="Lace & Leather Arcane Studio"
OWNER="Black Stag Web Design"
RIGHTS_URL="https://blackstagweb.com/ownership.html"
MARKERS=(b"c2pa",b"jumbf",b"content credentials",b"contentcredentials")
CREDIT_FIELDS=(
    "XMP-dc:Creator","EXIF:Artist","IPTC:By-line",
    "XMP-dc:Rights","EXIF:Copyright","IPTC:CopyrightNotice",
    "XMP-xmpRights:Owner","XMP-photoshop:Credit",
)
DANGEROUS=(
    "XMP-xmpRights:UsageTerms",
    "XMP-plus:LicensorName",
    "XMP-iptcExt:DigitalSourceType",
)
PNG_CONTENT={"IDAT","PLTE","tRNS","acTL","fcTL","fdAT"}


def digest(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def meta(path:Path)->dict:
    r=subprocess.run(
        ["exiftool","-j","-G1","-a","-s",str(path)],
        capture_output=True,text=True,check=True,
    )
    rows=json.loads(r.stdout)
    if len(rows)!=1:
        raise RuntimeError("unexpected_exiftool_record_count")
    return rows[0]


def protected(raw:bytes,m:dict)->bool:
    low=raw.lower()
    if any(marker in low for marker in MARKERS):
        return True
    return any(
        "c2pa" in key.lower()
        or "jumbf" in key.lower()
        or "contentcredentials" in key.lower()
        for key in m
    )


def conflicts(m:dict)->list[str]:
    allowed=(STUDIO.lower(),OWNER.lower())
    bad=[]
    for field in CREDIT_FIELDS:
        value=m.get(field)
        if value in (None,""):
            continue
        if isinstance(value,list):
            value=", ".join(map(str,value))
        low=str(value).lower()
        if not any(token in low for token in allowed):
            bad.append(field)
    for field in DANGEROUS:
        if m.get(field):
            bad.append(field)
    return sorted(set(bad))


def state(path:Path,mode="RGBA")->dict:
    with Image.open(path) as im:
        frames=getattr(im,"n_frames",1)
        if frames!=1:
            raise RuntimeError("animated_or_multiframe")
        im.load()
        pix=im.convert(mode)
        icc=im.info.get("icc_profile") or b""
        if not isinstance(icc,bytes):
            icc=str(icc).encode("utf-8")
        out={
            "format":im.format,
            "size":list(im.size),
            "frames":frames,
            "pixel_sha256":digest(pix.tobytes()),
            "icc_sha256":digest(icc),
        }
        if mode=="RGBA":
            out["alpha_sha256"]=digest(pix.getchannel("A").tobytes())
        return out


def png_picture_hash(data:bytes)->str:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not_png")
    parts=[]
    cursor=8
    while cursor+12<=len(data):
        count=int.from_bytes(data[cursor:cursor+4],"big")
        tag=data[cursor+4:cursor+8].decode("ascii")
        end=cursor+count+12
        if end>len(data):
            raise ValueError("truncated_png")
        if tag in PNG_CONTENT:
            parts.append(data[cursor+4:cursor+8+count])
        cursor=end
        if tag=="IEND":
            break
    if not parts:
        raise RuntimeError("no_png_picture_payload")
    return digest(b"".join(parts))


def required(entry:dict)->dict:
    return {
        "XMP-dc:Creator":STUDIO,
        "XMP-dc:Rights":entry["rights"],
        "XMP-dc:Description":entry["description"],
        "XMP-dc:Source":STUDIO,
        "XMP-photoshop:Credit":STUDIO+" (concept artwork production and preparation)",
        "XMP-xmpRights:WebStatement":RIGHTS_URL,
    }


def matches(m:dict,entry:dict)->bool:
    for key,expected in required(entry).items():
        actual=m.get(key)
        if isinstance(actual,list):
            actual=", ".join(map(str,actual))
        if str(actual or "")!=expected:
            return False
    return True


def write_meta(path:Path,entry:dict)->None:
    cmd=["exiftool","-overwrite_original","-P"]
    cmd += [f"-{key}={value}" for key,value in required(entry).items()]
    cmd.append(str(path))
    r=subprocess.run(cmd,capture_output=True,text=True)
    if r.returncode!=0 or "1 image files updated" not in r.stdout:
        raise RuntimeError("metadata_write_failed")


def metadata_only(path:Path,entry:dict,raw:bytes,before:dict,before_meta:dict)->dict:
    payload=png_picture_hash(raw)
    if matches(before_meta,entry):
        return {
            "status":"already_credited",
            "operation":"metadata_only",
            "format":"PNG",
            "dimensions":before["size"],
            "output_sha256":digest(raw),
        }
    try:
        write_meta(path,entry)
        updated=path.read_bytes()
        after=state(path,"RGBA")
        after_payload=png_picture_hash(updated)
        after_meta=meta(path)
        if before!=after or payload!=after_payload:
            raise RuntimeError("png_content_changed")
        if protected(updated,after_meta):
            raise RuntimeError("unexpected_authenticity_marker")
        if not matches(after_meta,entry):
            raise RuntimeError("metadata_readback_failed")
    except Exception:
        path.write_bytes(raw)
        raise
    return {
        "status":"verified",
        "operation":"metadata_only",
        "format":"PNG",
        "dimensions":before["size"],
        "output_sha256":digest(updated),
        "pixels_alpha_frames_profile_unchanged":True,
        "compressed_picture_data_unchanged":True,
    }


def repair_jpeg_to_png(path:Path,entry:dict,raw:bytes,before_meta:dict)->dict:
    before=state(path,"RGB")
    if before["format"]!="JPEG":
        raise RuntimeError("detected_format_not_jpeg")
    orientation=before_meta.get("EXIF:Orientation")
    if orientation not in (None,"",1,"1","Horizontal (normal)"):
        raise RuntimeError(f"non_normal_orientation:{orientation}")
    temp=path.with_name(path.name+".repair-temp")
    try:
        with Image.open(path) as src:
            src.load()
            rgb=src.convert("RGB")
            kwargs={"format":"PNG","optimize":False,"compress_level":6}
            icc=src.info.get("icc_profile")
            if icc:
                kwargs["icc_profile"]=icc
            rgb.save(temp,**kwargs)
        write_meta(temp,entry)
        repaired=temp.read_bytes()
        if not repaired.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("repair_output_not_png")
        after=state(temp,"RGB")
        after_meta=meta(temp)
        if after["format"]!="PNG":
            raise RuntimeError("repair_output_not_png_format")
        if before["size"]!=after["size"]:
            raise RuntimeError("dimensions_changed")
        if before["pixel_sha256"]!=after["pixel_sha256"]:
            raise RuntimeError("decoded_rgb_pixels_changed")
        if before["icc_sha256"]!=after["icc_sha256"]:
            raise RuntimeError("icc_profile_changed")
        if protected(repaired,after_meta):
            raise RuntimeError("unexpected_authenticity_marker")
        if not matches(after_meta,entry):
            raise RuntimeError("metadata_readback_failed")
        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True)
        path.write_bytes(raw)
        raise
    return {
        "status":"verified",
        "operation":"jpeg_bytes_to_true_png",
        "source_container_format":"JPEG",
        "output_container_format":"PNG",
        "dimensions":before["size"],
        "output_sha256":digest(path.read_bytes()),
        "decoded_rgb_pixels_unchanged":True,
        "icc_profile_unchanged":True,
    }


def process(entry:dict)->dict:
    rel=Path(entry["path"])
    if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower()!=".png":
        raise ValueError(f"unsafe_target:{rel}")
    path=(ROOT/rel).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError(f"missing_target:{rel}")
    if not rel.as_posix().startswith("stag-studio/"):
        raise ValueError(f"outside_legacy_scope:{rel}")

    raw=path.read_bytes()
    source_sha=digest(raw)
    rec={
        "path":rel.as_posix(),
        "project":entry["project"],
        "rights":entry["rights"],
        "source_sha256":source_sha,
    }
    if len(raw)>15_000_000:
        rec.update(status="held_for_review",reason="file_exceeds_batch_limit",output_sha256=source_sha)
        return rec

    try:
        before_meta=meta(path)
        detected=state(path,"RGBA")
    except Exception as exc:
        rec.update(status="held_for_review",reason="unreadable_image",detail=type(exc).__name__,output_sha256=source_sha)
        return rec

    if protected(raw,before_meta):
        rec.update(status="held_for_review",reason="existing_authenticity_credentials",output_sha256=source_sha)
        return rec
    bad=conflicts(before_meta)
    if bad:
        rec.update(status="held_for_review",reason="conflicting_creator_or_rights",conflicting_fields=bad,output_sha256=source_sha)
        return rec

    try:
        if detected["format"]=="PNG":
            result=metadata_only(path,entry,raw,detected,before_meta)
        elif detected["format"]=="JPEG" and raw.startswith(b"\xff\xd8"):
            result=repair_jpeg_to_png(path,entry,raw,before_meta)
        else:
            rec.update(status="held_for_review",reason="unapproved_format",detected_format=detected["format"],output_sha256=source_sha)
            return rec
    except Exception:
        path.write_bytes(raw)
        raise

    rec.update(result)
    if rec["status"]=="verified":
        rec.update(
            creator=STUDIO,
            rights_holder=OWNER,
            studio_credit=STUDIO+" (concept artwork production and preparation)",
            rights_statement_url=RIGHTS_URL,
        )
    return rec


def run(manifest_path:Path,report_path:Path)->None:
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("production_studio")!=STUDIO:
        raise ValueError("unexpected_production_studio")
    entries=manifest.get("files") or []
    if len(entries)!=10 or len({entry["path"] for entry in entries})!=10:
        raise ValueError("concept_batch_requires_ten_unique_files")

    rows=[]
    for entry in entries:
        row=process(entry)
        rows.append(row)
        print(row["status"],row.get("operation",""),row["path"],flush=True)

    verified=[row for row in rows if row["status"]=="verified"]
    already=[row for row in rows if row["status"]=="already_credited"]
    held=[row for row in rows if row["status"]=="held_for_review"]
    if not verified and not already:
        raise RuntimeError("nothing_safely_processable")

    report={
        "schema_version":1,
        "batch":manifest["batch"],
        "classification_basis":"Historical Black Stag portfolio copy explicitly labeled these projects as concept demos.",
        "historical_evidence_commit":"0551bef616a4a9c95cdccebceeb40c65358cdf48",
        "production_studio":STUDIO,
        "rights_holder":OWNER,
        "total":len(rows),
        "verified":len(verified),
        "already_credited":len(already),
        "held_for_review":len(held),
        "updated_paths":[row["path"] for row in verified],
        "held_paths":[{"path":row["path"],"reason":row["reason"]} for row in held],
        "visual_review":"pending",
        "live_site_code_changed":False,
        "files":rows,
    }
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",default="studio/bswd-legacy-concept-batch01.json")
    ap.add_argument("--report",default="studio/bswd-legacy-concept-batch01-results.json")
    args=ap.parse_args()
    run(ROOT/args.manifest,ROOT/args.report)
