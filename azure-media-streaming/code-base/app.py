from azure.storage.blob import ContentSettings

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    blob_client = container_client.get_blob_client(file.filename)
    content_settings = ContentSettings(
        content_type=file.content_type or "video/mp4",
        cache_control="public, max-age=31536000"  # ← NEW: 1 year browser cache
    )
    blob_client.upload_blob(
        file.file,
        overwrite=True,
        content_settings=content_settings
    )
    return RedirectResponse("/", status_code=303)   
