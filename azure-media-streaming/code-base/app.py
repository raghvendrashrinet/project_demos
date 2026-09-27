import os
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from datetime import timedelta

app = FastAPI()

# --- Config (use env vars in production) ---
ACCOUNT_URL = os.getenv("AZURE_STORAGE_ACCOUNT_URL", "https://<account>.blob.core.windows.net")
CONTAINER   = os.getenv("AZURE_BLOB_CONTAINER", "videos")

# Auth: works with Managed Identity (AKS/App Service) or local Azure CLI
blob_service_client = BlobServiceClient.from_connection_string(
    os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
    credential=DefaultAzureCredential()
)
container_client = blob_service_client.get_container_client(CONTAINER)

# Ensure container exists
try:
    container_client.get_container_properties()
except Exception:
    container_client.create_container()


# ---------- HTML ----------
@app.get("/", response_class=HTMLResponse)
def index():
    videos = []
    for blob in container_client.list_blobs(name_starts_with=""):
        if blob.name.lower().endswith((".mp4", ".webm", ".mov")):
            # Generate a 1-hour SAS URL for playback
            from azure.storage.blob import generate_blob_sas, BlobSasPermissions
            sas_token = generate_blob_sas(
                account_name=ACCOUNT_URL.split(".")[1].replace("blob.core.windows.net", ""),
                container_name=CONTAINER,
                blob_name=blob.name,
                account_key=os.getenv("AZURE_STORAGE_ACCOUNT_KEY"),  # or use credential
                permission=BlobSasPermissions(read=True),
                expiry=timedelta(hours=1),
            )
            url = f"{ACCOUNT_URL}/{CONTAINER}/{blob.name}?{sas_token}"
            videos.append({"name": blob.name, "url": url, "size_mb": round(blob.size / 1024 / 1024, 1)})

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Video Platform</title>
    <style>
      body {{ font-family: sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
      video {{ width: 100%; border-radius: 8px; margin-bottom: 1rem; }}
      .video-item {{ margin: 1rem 0; padding: 1rem; border: 1px solid #ddd; border-radius: 8px; }}
      .video-item h3 {{ margin: 0 0 0.5rem; }}
      .meta {{ color: #666; font-size: 0.85rem; }}
    </style>
    </head>
    <body>
    <h1>🎬 Video Platform</h1>
    <form action="/upload" method="POST" enctype="multipart/form-data">
      <input type="file" name="file" accept="video/*" required>
      <button type="submit">Upload</button>
    </form>
    <hr>
    {''.join(f'''
    <div class="video-item">
      <h3>{v["name"]}</h3>
      <p class="meta">{v["size_mb"]} MB</p>
      <video controls preload="metadata">
        <source src="{v["url"]}" type="video/mp4">
      </video>
    </div>''' for v in videos)}
    </body>
    </html>
    """


# ---------- Upload ----------
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    blob_client = container_client.get_blob_client(file.filename)
    blob_client.upload_blob(file.file, overwrite=True,
                            content_type=file.content_type or "video/mp4")
    return RedirectResponse("/", status_code=303)   
