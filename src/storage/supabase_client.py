import requests
import os

def upload_audio_to_supabase(audio_path, filename, supabase_url, supabase_key, bucket="audio-records"):
    """
    Uploads a local audio file to Supabase Storage using the direct REST API.
    Returns the public URL of the uploaded file if successful, otherwise None.
    """
    # URL structure for uploading file to Supabase storage
    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{filename}"
    
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "audio/wav"
    }
    
    try:
        if not os.path.exists(audio_path):
            print(f"[Supabase Storage] Local audio file does not exist: {audio_path}")
            return None
            
        print(f"[Supabase Storage] Uploading {filename} to Supabase Storage...")
        with open(audio_path, "rb") as f:
            response = requests.post(url, headers=headers, data=f, timeout=30)
            
        if response.status_code == 200:
            # Generate the public URL
            public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket}/{filename}"
            print(f"[Supabase Storage] Upload successful! Public URL: {public_url}")
            return public_url
        else:
            print(f"[Supabase Storage Error] Upload failed with status code {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        print(f"[Supabase Storage Error] Failed to upload audio: {e}")
        return None
