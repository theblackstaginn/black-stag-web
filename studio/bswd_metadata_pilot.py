#!/usr/bin/env python3
import argparse, hashlib, json, subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STUDIO = "Lace & Leather Arcane Studio"
OWNER = "Black Stag Web Design"
RIGHTS = "Copyright 2026 Black Stag Web Design"
WEB = "https://blackstagweb.com/ownership.html"
SUPPORTED = {".png",".jpg",".jpeg",".webp"}
CONTENT = {".png":{"IDAT","PLTE","tRNS","acTL","fcTL","fdAT"}, ".webp":{"VP8 ","VP8L","ALPH","ANIM","ANMF"}}
MARKERS=(b"c2pa",b"jumbf",b"content credentials",b"contentcredentials")
CREDIT_FIELDS=("XMP-dc:Creator","EXIF:Artist","IPTC:By-line","XMP-dc:Rights","EXIF:Copyright","IPTC:CopyrightNotice","XMP-xmpRights:Owner","XMP-photoshop:Credit")

def digest(b): return hashlib.sha256(b).hexdigest()

def image_state(path):
    with Image.open(path) as im:
        if getattr(im,"n_frames",1)!=1: raise RuntimeError("animated")
        im.load(); rgba=im.convert("RGBA"); alpha=rgba.getchannel("A"); icc=im.info.get("icc_profile") or b""
        if not isinstance(icc,bytes): icc=str(icc).encode()
        return {"format":im.format,"size":list(im.size),"pixel_sha256":digest(rgba.tobytes()),"alpha_sha256":digest(alpha.tobytes()),"icc_sha256":digest(icc)}

def picture_hash(data,suffix):
    parts=[]
    if suffix==".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"): raise ValueError("not png")
        p=8
        while p+12<=len(data):
            n=int.from_bytes(data[p:p+4],"big"); tag=data[p+4:p+8].decode("ascii"); end=p+n+12
            if end>len(data): raise ValueError("truncated png")
            if tag in CONTENT[suffix]: parts.append(data[p+4:p+8+n])
            p=end
            if tag=="IEND": break
    elif suffix==".webp":
        if not(data.startswith(b"RIFF") and data[8:12]==b"WEBP"): raise ValueError("not webp")
        p=12
        while p+8<=len(data):
            n=int.from_bytes(data[p+4:p+8],"little"); tag=data[p:p+4].decode("ascii"); end=p+8+n
            if end>len(data): raise ValueError("truncated webp")
            if tag in CONTENT[suffix]: parts.append(data[p:end])
            p=end+(n%2)
    else:
        if not data.startswith(b"\xff\xd8"): raise ValueError("not jpeg")
        p=2
        while p<len(data)-4:
            if data[p]!=0xff: raise ValueError("jpeg")
            while data[p]==0xff: p+=1
            marker=data[p]; p+=1
            if marker in (0xd8,0xd9,0x01) or 0xd0<=marker<=0xd7: continue
            n=int.from_bytes(data[p:p+2],"big")
            if n<2: raise ValueError("jpeg")
            if marker==0xda:
                parts.append(data[p+n:]); break
            p+=n
    if not parts: raise RuntimeError("no picture payload")
    return digest(b"".join(parts))

def meta(path):
    out=subprocess.run(["exiftool","-j","-G1","-a","-s",str(path)],capture_output=True,text=True,check=True)
    rows=json.loads(out.stdout)
    if len(rows)!=1: raise RuntimeError("exiftool")
    return rows[0]

def protected(raw,m):
    low=raw.lower()
    return any(x in low for x in MARKERS) or any(("c2pa" in k.lower() or "jumbf" in k.lower() or "contentcredentials" in k.lower()) for k in m)

def conflicts(m):
    ok=(STUDIO.lower(),OWNER.lower())
    bad=[]
    for k in CREDIT_FIELDS:
        v=m.get(k)
        if not v: continue
        if isinstance(v,list): v=", ".join(map(str,v))
        if not any(t in str(v).lower() for t in ok): bad.append(k)
    for k in ("XMP-xmpRights:UsageTerms","XMP-plus:LicensorName","XMP-iptcExt:DigitalSourceType"):
        if m.get(k): bad.append(k)
    return sorted(set(bad))

def required(desc):
    return {"XMP-dc:Creator":STUDIO,"XMP-dc:Rights":RIGHTS,"XMP-dc:Description":desc,"XMP-dc:Source":STUDIO,"XMP-photoshop:Credit":STUDIO+" (artwork production and preparation)","XMP-xmpRights:WebStatement":WEB}

def matches(m,desc):
    for k,v in required(desc).items():
        got=m.get(k)
        if isinstance(got,list): got=", ".join(map(str,got))
        if str(got or "")!=v: return False
    return True

def run(manifest_path,report_path):
    manifest=json.loads(manifest_path.read_text())
    if manifest.get("project")!=OWNER or manifest.get("production_studio")!=STUDIO or manifest.get("rights")!=RIGHTS: raise ValueError("manifest identity mismatch")
    rows=[]
    for e in manifest["files"]:
        rel=Path(e["path"]); p=(ROOT/rel).resolve(); suffix=rel.suffix.lower()
        if rel.is_absolute() or ".." in rel.parts or suffix not in SUPPORTED or not p.is_file() or not p.is_relative_to(ROOT): raise ValueError(str(rel))
        raw=p.read_bytes(); rec={"path":rel.as_posix(),"source_sha256":digest(raw),"rights_basis":e["rights_basis"]}
        try:
            before=image_state(p); payload=picture_hash(raw,suffix); m=meta(p)
        except Exception as exc:
            rec.update(status="held_for_review",reason="unsupported_or_unreadable",detail=type(exc).__name__,output_sha256=digest(raw)); rows.append(rec); continue
        rec.update(format=before["format"],dimensions=before["size"],pixel_sha256=before["pixel_sha256"],encoded_picture_sha256=payload)
        bad=conflicts(m)
        if protected(raw,m) or bad:
            rec.update(status="held_for_review",reason="protected_provenance" if protected(raw,m) else "conflicting_rights",conflicting_fields=bad,output_sha256=digest(raw)); rows.append(rec); continue
        desc=e["description"]
        if matches(m,desc):
            rec.update(status="already_credited",output_sha256=digest(raw)); rows.append(rec); continue
        cmd=["exiftool","-overwrite_original","-P"]+[f"-{k}={v}" for k,v in required(desc).items()]+[str(p)]
        try:
            result=subprocess.run(cmd,capture_output=True,text=True)
            if result.returncode!=0 or "1 image files updated" not in result.stdout: raise RuntimeError("write failed")
            updated=p.read_bytes(); after=image_state(p); after_payload=picture_hash(updated,suffix); after_m=meta(p)
            if before!=after or payload!=after_payload: raise RuntimeError("picture changed")
            if protected(updated,after_m) or not matches(after_m,desc): raise RuntimeError("metadata verification failed")
        except Exception:
            p.write_bytes(raw); raise
        rec.update(status="verified_metadata_only",output_sha256=digest(updated),pixels_alpha_frames_profile_unchanged=True,compressed_picture_data_unchanged=True,creator=STUDIO,rights=RIGHTS,studio_credit=STUDIO+" (artwork production and preparation)")
        rows.append(rec)
    verified=[r for r in rows if r["status"]=="verified_metadata_only"]; held=[r for r in rows if r["status"]=="held_for_review"]
    if not verified and not any(r["status"]=="already_credited" for r in rows): raise RuntimeError("nothing safely processable")
    report={"schema_version":1,"pilot":"BSWD metadata provenance pilot","project_owner":OWNER,"production_studio":STUDIO,"total":len(rows),"verified_metadata_only":len(verified),"held_for_review":len(held),"updated_paths":[r["path"] for r in verified],"live_site_code_changed":False,"files":rows}
    report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--manifest",default="studio/bswd-pilot-manifest.json"); ap.add_argument("--report",default="studio/bswd-pilot-results.json"); a=ap.parse_args()
    run(ROOT/a.manifest,ROOT/a.report)
