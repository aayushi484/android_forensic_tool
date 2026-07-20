import os
import hashlib

def recover_trashed_files(case_media_paths: list[str]) -> list[dict]:
    """Recover files from Android's .Trash / .trashed-* locations.
    
    Honest scope: recovers files still sitting in soft-delete locations
    (scoped storage since Android 11). Does NOT claim unallocated-space
    file-fragment recovery (requires raw block access, non-root ADB
    genuinely does not provide).
    
    Returns list of dicts: {'original_path': str, 'trash_path': str,
    'file_hash': str, 'size': int, 'recovery_method': 'trash_recovery'}
    """
    recovered = []
    target_patterns = ['.Trash', '.trashed-', 'DCIM/.thumbnails', '.pending-']
    
    for base_path in case_media_paths:
        for root, dirs, files in os.walk(base_path):
            for file in files:
                file_path = os.path.join(root, file)
                
                is_target = False
                for pattern in target_patterns:
                    if pattern in file_path:
                        is_target = True
                        break
                        
                if is_target:
                    sha256 = hashlib.sha256()
                    try:
                        with open(file_path, 'rb') as f:
                            for chunk in iter(lambda: f.read(4096), b""):
                                sha256.update(chunk)
                        file_hash = sha256.hexdigest()
                        size = os.path.getsize(file_path)
                        
                        original_path = file
                        if '.trashed-' in file:
                            parts = file.split('-', 2)
                            if len(parts) >= 3:
                                original_path = parts[2]
                                
                        recovered.append({
                            'original_path': original_path,
                            'trash_path': file_path,
                            'file_hash': file_hash,
                            'size': size,
                            'recovery_method': 'trash_recovery'
                        })
                    except Exception:
                        pass
                        
    return recovered
