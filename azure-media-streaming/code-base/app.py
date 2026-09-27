"""
Video Streaming Platform — Azure Blob Storage backend
Architecture: FastAPI (control plane) → Blob Storage (media origin, direct to browser)
"""

import os
from datetime import timedelta, datetime, timezone
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
)

# ──────────────────────────────────────────────
# Config (set via environment variables)
# ──────────────────────────────────────────────
ACCOUNT_URL = os.getenv(
    "AZURE_STORAGE_ACCOUNT_URL",
    "https://<your-account>.blob.core.windows.net",
)
CONTAINER = os.getenv("AZURE_BLOB_CONTAINER", "videos")
SAS_TTL_MINUTES = int(os.getenv("SAS_TTL_MINUTES", "15"))  # short-lived
ALLOWED_EXTENSIONS = {".mp4", ".webm", ".mov", ".m3u8"}

# ──────────────────────────────────────────────
# Azure clients
# ──────────────────────────────────────────────
credential = DefaultAzureCredential()

blob_service_client = BlobServiceClient.from_connection_string(
    os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
    credential=credential,
)
container_client = blob_service_client.get_container_client(CONTAINER)

# Ensure container exists
try:
    container_client.get_container_properties()
except Exception:
    container_client.create_container()

# Extract account name for SAS generation
ACCOUNT_NAME = ACCOUNT_URL.split(".")[1].replace("blob.core.windows.net", "")

# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────
app = FastAPI(title="Video Platform")


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def generate_sas_url(blob_name: str, ttl_minutes: int = SAS_TTL_MINUTES) -> str:
    """Generate a short-lived read-only SAS URL for a blob."""
    sas_token = generate_blob_sas(
        account_name=ACCOUNT_NAME,
        container_name=CONTAINER,
        blob_name=blob_name,
        account_key=os.getenv("AZURE_STORAGE_ACCOUNT_KEY"),
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        protocol="https",
    )
    return f"{ACCOUNT_URL}/{CONTAINER}/{blob_name}?{sas_token}"


def list_videos() -> list[dict]:
    """List all video blobs with metadata and SAS URLs."""
    videos = []
    for blob in container_client.list_blobs(name_starts_with=""):
        ext = os.path.splitext(blob.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        videos.append(
            {
                "name": blob.name,
                "url": generate_sas_url(blob.name),
                "size_mb": round(blob.size / (1024 * 1024), 1),
                "uploaded": blob.last_modified.strftime("%Y-%m-%d %H:%M") if blob.last_modified else "—",
            }
        )
    videos.sort(key=lambda v: v["uploaded"], reverse=True)
    return videos


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index():
    videos = list_videos()
    video_cards = "\n".join(
        f'''
    <div class="video-item">
      <h3>{v["name"]}</h3>
      <p class="meta">{v["size_mb"]} MB · {v["uploaded"]}</p>
      <video controls preload="metadata" style="width:100%;border-radius:8px;">
        <source src="{v["url"]}" type="video/mp4">
        Your browser does not support the video tag.
      </video>
    </div>'''
        for v in videos
    )

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Video Platform</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           max-width: 960px; margin: 2rem auto; padding: 0 1rem; background: #f8f9fa; }}
    h1 {{ color: #1a1a2e; }}
    .upload-box {{ background: #fff; padding: 1.5rem; border-radius: 10px;
                  box-shadow: 0 1px 3px rgba(0,0,0,.1); margin-bottom: 2rem; }}
    .upload-box input[type=file] {{ margin-right: 0.5rem; }}
    .upload-box button {{ padding: 0.5rem 1.2rem; background: #2563eb; color: #fff;
                          border: none; border-radius: 6px; cursor: pointer; font-size: 1rem; }}
    .upload-box button:hover {{ background: #1d4ed8; }}
    .video-item {{ background: #fff; padding: 1.25rem; border-radius: 10px;
                  box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 1.25rem; }}
    .video-item h3 {{ margin: 0 0 0.25rem; font-size: 1.05rem; color: #1a1a2e; }}
    .meta {{ color: #6b7280; font-size: 0.85rem; margin: 0 0 0.75rem; }}
    .empty {{ text-align: center; color: #9ca3af; padding: 3rem; }}
  </style>
</head>
<body>
  <h1>🎬 Video Platform</h1>

  <div class="upload-box">
    <form action="/upload" method="POST" enctype="multipart/form-data">
      <input type="file" name="file" accept="video/*" required>
      <button type="submit">Upload</button>
    </form>
  </div>

  <hr style="border:none;border-top:1px solid #e5e7eb;margin:1.5rem 0;">

  {video_cards if videos else '<p class="empty">No videos yet. Upload one above.</p>'}
</body>
</html>
"""


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # Optional: size limit (e.g. 2 GB)
    MAX_SIZE = 2 * 1024 * 1024 * 1024
    file.file.seek(0, 2)
    if file.file.tell() > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 2 GB)")
    file.file.seek(0)

    blob_client = container_client.get_blob_client(file.filename)
    content_settings = ContentSettings(
        content_type=file.content_type or "video/mp4",
        cache_control="public, max-age=31536000",  # 1-year browser cache
    )
    blob_client.upload_blob(
        file.file,
        overwrite=True,
        content_settings=content_settings,
        content_type=file.content_type or "video/mp4",
    )
    return RedirectResponse("/", status_code=303)


@app.get("/api/videos")
def api_list_videos():
    """JSON API — useful for SPA / mobile clients."""
    return list_videos()


@app.get("/api/videos/{blob_name:path}")
def api_get_video_url(blob_name: str):
    """Return a fresh SAS URL for a specific video."""
    blob_client = container_client.get_blob_client(blob_name)
    try:
        blob_client.get_blob_properties()
    except Exception:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"url": generate_sas_url(blob_name)}


@app.get("/health")
def health():
    return {"status": "ok"}


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)   
