#!/usr/bin/env python3
"""Guarded provenance batch for four live Black Stag portfolio/site assets.

Supports two safe operations:
1) metadata-only updates when the file container matches its extension, and
2) true-PNG repair when a .png path actually contains JPEG bytes.

All writes preserve decoded pixels and ICC profile. Metadata-only writes also
preserve the encoded picture payload. Existing authenticity credentials,
conflicting rights, animation, unusual orientation, or any integrity mismatch
causes a hold/abort rather than a forced change.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
STUDIO="Lace & Leather Arcane Studio"
BSWD="Black Stag Web Design"
RIGHTS_URL="https://blackstagweb.com/ownership.html"
SUPPORTED={".png":"PNG",".jpg":"JPEG",".jpeg":"JPEG",".webp":"WEBP"}
CONTENT={".png":{"IDAT","PLTE","tRNS","acTL","fcTL","fdAT"},".webp":{"VP8 ","VP8L","ALPH","ANIM","ANMF"}}
MARKERS=(b"c2pa",b"jumbf",b"content credentials",b"contentcredentials")
CREDIT_FIELDS=("XMP-dc:Creator","EXIF:Artist","IPTC:By-line","XMP-dc:Rights","EXIF:Copyright","IPTC:CopyrightNotice","XMP-xmpRights:Owner","XMP-photoshop:Credit")
DANGEROUS=("XMP-xmpRights:UsageTerms","XMP-plus:LicensorName","XMP-iptcExt:DigitalSourceType")


def digest(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def meta(path:Path)->dict:
    r=subprocess.run(["exiftool","-j","-G1","-a","-s",str(path)],capture_output=True,text=True,check=True)
    rows=json.loads(r.stdout)
    if len(rows)!=1:
        raise RuntimeError("unexpected_exiftool_record_count")
    return rows[0]


def protected(raw:bytes,m:dict)->bool:
    low=raw.lower()
    if any(x in low for x in MARKERS):
        return True
    return any("c2pa" in k.lower() or "jumbf" in k.lower() or "contentcredentials" in k.lower() for k in m)


def conflicts(m:dict,project:str)->list[str]:
    allowed=(STUDIO.lower(),BSWD.lower(),project.lower())
    bad=[]
    for k in CREDIT_FIELDS:
        v=m.get(k)
        if v in (None,""):
            continue
        if isinstance(v,list):
            v=", ".join(map(str,v))
        if not any(token in str(v).lower() for token in allowed):
            bad.append(k)
    for k in DANGEROUS:
        if m.get(k):
            bad.append(k)
    return sorted(set(bad))


def state(path:Path, mode="RGBA")->dict:
    with Image.open(path) as im:
        frames=getattr(im,"n_frames",1)
        if frames!=1:
            raise RuntimeError("animated_or_multiframe")
        im.load()
        pix=im.convert(mode)
        icc=im.info.get("icc_profile") or b""
        if not isinstance(icc,bytes):
            icc=str(icc).encode()
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


def picture_hash(data:bytes,suffix:str)->str:
    parts=[]
    if suffix==".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("not_png")
        p=8
        while p+12<=len(data):
            n=int.from_bytes(data[p:p+4],"big")
            tag=data[p+4:p+8].decode("ascii")
            end=p+n+12
            if end>len(data):
                raise ValueError("truncated_png")
            if tag in CONTENT[suffix]:
                parts.append(data[p+4:p+8+n])
            p=end
            if tag=="IEND":
                break
    elif suffix==".webp":
        if not(data.startswith(b"RIFF") and data[8:12]==b"WEBP"):
            raise ValueError("not_webp")
        p=12
        while p+8<=len(data):
            n=int.from_bytes(data[p+4:p+8],"little")
            tag=data[p:p+4].decode("ascii")
            end=p+8+n
            if end>len(data):
                raise ValueError("truncated_webp")
            if tag in CONTENT[suffix]:
                parts.append(data[p:end])
            p=end+(n%2)
    elif suffix in {".jpg",".jpeg"}:
        if not data.startswith(b"\xff\xd8"):
            raise ValueError("not_jpeg")
        p=2
        while p<len(data)-4:
            if data[p]!=0xff:
                raise ValueError("unexpected_jpeg_segment")
            while data[p]==0xff:
                p+=1
            marker=data[p]
            p+=1
            if marker in (0xd8,0xd9,0x01) or 0xd0<=marker<=0xd7:
                continue
            n=int.from_bytes(data[p:p+2],"big")
            if n<2:
                raise ValueError("malformed_jpeg")
            if marker==0xda:
                parts.append(data[p+n:])
                break
            p+=n
    if not parts:
        raise RuntimeError("no_picture_payload")
    return digest(b"".join(parts))


def required(entry:dict)->dict:
    return {
        "XMP-dc:Creator":STUDIO,
        "XMP-dc:Rights":entry["rights"],
        "XMP-dc:Description":entry["description"],
        "XMP-dc:Source":STUDIO,
        "XMP-photoshop:Credit":STUDIO+" (artwork production and preparation)",
        "XMP-xmpRights:WebStatement":RIGHTS_URL,
    }


def matches(m:dict,entry:dict)->bool:
    for k,v in required(entry).items():
        got=m.get(k)
        if isinstance(got,list):
            got=", ".join(map(str,got))
        if str(got or "")!=v:
            return False
    return True


def write_meta(path:Path,entry:dict)->None:
    cmd=["exiftool","-overwrite_original","-P"]+[f"-{k}={v}" for k,v in required(entry).items()]+[str(path)]
    r=subprocess.run(cmd,capture_output=True,text=True)
    if r.returncode!=0 or "1 image files updated" not in r.stdout:
        raise RuntimeError("metadata_write_failed")


def metadata_only(path:Path,rel:Path,entry:dict,raw:bytes,before:dict,before_meta:dict)->dict:
    suffix=rel.suffix.lower()
    payload=picture_hash(raw,suffix)
    if matches(before_meta,entry):
        return {
            "status":"already_credited",
            "operation":"metadata_only",
            "output_sha256":digest(raw),
            "format":before["format"],
            "dimensions":before["size"],
        }
    try:
        write_meta(path,entry)
        updated=path.read_bytes()
        after=state(path,"RGBA")
        after_payload=picture_hash(updated,suffix)
        after_meta=meta(path)
        if before!=after or payload!=after_payload:
            raise RuntimeError("image_content_changed")
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
        "output_sha256":digest(updated),
        "format":before["format"],
        "dimensions":before["size"],
        "pixels_alpha_frames_profile_unchanged":True,
        "compressed_picture_data_unchanged":True,
    }


def repair_png_from_jpeg(path:Path,entry:dict,raw:bytes,before_meta:dict)->dict:
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
        "output_sha256":digest(path.read_bytes()),
        "source_container_format":"JPEG",
        "output_container_format":"PNG",
        "dimensions":before["size"],
        "decoded_rgb_pixels_unchanged":True,
        "icc_profile_unchanged":True,
    }


def process(entry:dict)->dict:
    rel=Path(entry["path"])
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe_path:{rel}")
    suffix=rel.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"unsupported_extension:{rel}")
    path=(ROOT/rel).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file() or not rel.as_posix().startswith("stag-studio/"):
        raise ValueError(f"invalid_path:{rel}")
    raw=path.read_bytes()
    rec={
        "path":rel.as_posix(),
        "project":entry["project"],
        "website":entry["website"],
        "rights":entry["rights"],
        "source_sha256":digest(raw),
    }
    if len(raw)>15_000_000:
        rec.update(status="held_for_review",reason="file_exceeds_batch_limit",output_sha256=digest(raw))
        return rec
    try:
        before_meta=meta(path)
        detected=state(path,"RGBA")
    except Exception as exc:
        rec.update(status="held_for_review",reason="unreadable_image",detail=type(exc).__name__,output_sha256=digest(raw))
        return rec
    if protected(raw,before_meta):
        rec.update(status="held_for_review",reason="existing_authenticity_credentials",output_sha256=digest(raw))
        return rec
    bad=conflicts(before_meta,entry["project"])
    if bad:
        rec.update(status="held_for_review",reason="conflicting_creator_or_rights",conflicting_fields=bad,output_sha256=digest(raw))
        return rec
    try:
        if detected["format"]==SUPPORTED[suffix]:
            result=metadata_only(path,rel,entry,raw,detected,before_meta)
        elif suffix==".png" and detected["format"]=="JPEG" and raw.startswith(b"\xff\xd8"):
            result=repair_png_from_jpeg(path,entry,raw,before_meta)
        else:
            rec.update(status="held_for_review",reason="unapproved_format_mismatch",detected_format=detected["format"],output_sha256=digest(raw))
            return rec
    except Exception:
        path.write_bytes(raw)
        raise
    rec.update(result)
    if rec["status"]=="verified":
        rec.update(
            creator=STUDIO,
            studio_credit=STUDIO+" (artwork production and preparation)",
            rights_statement_url=RIGHTS_URL,
        )
    return rec


def run(manifest_path:Path,report_path:Path)->None:
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("production_studio")!=STUDIO:
        raise ValueError("unexpected_production_studio")
    entries=manifest.get("files") or []
    if len(entries)!=4 or len({e["path"] for e in entries})!=4:
        raise ValueError("batch_requires_four_unique_files")
    rows=[]
    for entry in entries:
        row=process(entry)
        rows.append(row)
        print(row["status"],row.get("operation",""),row["path"],flush=True)
    verified=[r for r in rows if r["status"]=="verified"]
    already=[r for r in rows if r["status"]=="already_credited"]
    held=[r for r in rows if r["status"]=="held_for_review"]
    if not verified and not already:
        raise RuntimeError("nothing_safely_processable")
    report={
        "schema_version":1,
        "batch":manifest["batch"],
        "production_studio":STUDIO,
        "total":len(rows),
        "verified":len(verified),
        "already_credited":len(already),
        "held_for_review":len(held),
        "updated_paths":[r["path"] for r in verified],
        "held_paths":[{"path":r["path"],"reason":r["reason"]} for r in held],
        "visual_review":"pending",
        "live_site_code_changed":False,
        "files":rows,
    }
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",default="studio/bswd-live-asset-batch02.json")
    ap.add_argument("--report",default="studio/bswd-live-asset-batch02-results.json")
    args=ap.parse_args()
    run(ROOT/args.manifest,ROOT/args.report)
