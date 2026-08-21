# export_utils.py
import io
import time
from pathlib import Path
import ee
import geemap
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


def get_drive_service():
    """Reuses the OAuth credentials already granted to ee.Authenticate()."""
    creds = ee.data.get_persistent_credentials()
    return build("drive", "v3", credentials=creds)


def wait_for_task(task, poll_interval=15):
    """Blocks until an ee.batch.Task finishes."""
    task.start()
    while task.active():
        print(f"  ⏳ Task {task.id} running...")
        time.sleep(poll_interval)
    status = task.status()
    if status["state"] != "COMPLETED":
        raise RuntimeError(f"Task failed: {status}")
    print(f"  ✅ Task {task.id} completed")
    return status


def download_from_drive(filename, folder_name, local_path, cleanup=False):
    """Finds a file by name inside a Drive folder, downloads it locally,
    and deletes it from Drive afterward (cleanup=True) to preserve space."""
    service = get_drive_service()

    folder_q = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
    folders = service.files().list(q=folder_q, fields="files(id)").execute().get("files", [])
    if not folders:
        raise FileNotFoundError(f"Drive folder '{folder_name}' not found")
    folder_id = folders[0]["id"]

    file_q = f"name = '{filename}' and '{folder_id}' in parents"
    files = service.files().list(q=file_q, fields="files(id, name)").execute().get("files", [])
    if not files:
        raise FileNotFoundError(f"'{filename}' not found in Drive folder '{folder_name}'")

    file_id = files[0]["id"]
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(local_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    print(f"  ✅ Downloaded {filename} -> {local_path}")

    if cleanup:
        service.files().delete(fileId=file_id).execute()
        print(f"  🗑️ Deleted {filename} from Drive")

    return local_path


def _is_size_limit_error(e):
    msg = str(e).lower()
    return "bytes must be less than or equal to" in msg or "request payload size" in msg


def export_image_with_fallback(
    image,
    local_path,
    scale,
    region,
    drive_folder="GEE_exports",
    drive_filename=None,
):
    """
    Tries a direct local export first. geemap.ee_export_image swallows
    size-limit errors internally (prints, doesn't raise), so success is
    verified by checking the output file exists rather than by exception.
    """
    local_path = Path(local_path)

    try:
        geemap.ee_export_image(
            image,
            filename=str(local_path),
            scale=scale,
            region=region,
        )
    except Exception as e:
        if not _is_size_limit_error(e):
            raise
        print(f"  ⚠️ Local export raised size error, falling back to Drive: {e}")
        return _export_via_drive(image, local_path, scale, region, drive_folder, drive_filename)

    if local_path.exists() and local_path.stat().st_size > 0:
        print(f"  ✅ Saved locally: {local_path}")
        return str(local_path)

    print(f"  ⚠️ Local export produced no file (likely size limit), falling back to Drive")
    return _export_via_drive(image, local_path, scale, region, drive_folder, drive_filename)


def _export_via_drive(image, local_path, scale, region, drive_folder, drive_filename):
    filename = drive_filename or Path(local_path).name
    task = ee.batch.Export.image.toDrive(
        image=image,
        folder=drive_folder,
        fileNamePrefix=Path(filename).stem,
        region=region,
        scale=scale,
        maxPixels=1e10,
    )
    wait_for_task(task)
    return download_from_drive(filename, drive_folder, local_path, cleanup=True)