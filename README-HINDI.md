# ThugTools

Premium white theme, glassmorphism aur Flask backend wala complete responsive tools website.

## Folder structure

```text
AdarshToolsPro/
  backend/
    app.py
    requirements.txt
    uploads/
    downloads/
  frontend/
    index.html
    style.css
    script.js
    assets/
      logo.svg
    pages/
      youtube.html
      instagram.html
      pinterest.html
      upscale.html
      compress.html
      removebg.html
      audio.html
      thumbnail.html
      qr.html
      convert.html
      watermark.html
```

## Run karne ke steps

1. Terminal me project folder kholna:

```powershell
cd "C:\Users\welcome\OneDrive\Desktop\ADAARSH TOOLS\AdarshToolsPro\backend"
```

2. Virtual environment banana:

```powershell
python -m venv venv
```

3. Activate karna:

```powershell
venv\Scripts\activate
```

4. Dependencies install karna:

```powershell
pip install -r requirements.txt
```

5. MP3 conversion aur HD video merge ke liye FFmpeg install hona chahiye. Windows me easiest:

```powershell
winget install Gyan.FFmpeg
```

6. Server start karna:

```powershell
python app.py
```

7. Browser me open:

```text
http://127.0.0.1:5000
```

## Important notes

- YouTube, Instagram, Pinterest downloader public URLs par kaam karega. Private/login wali links ke liye cookies/auth setup chahiye hota hai.
- 1080p tabhi milega jab source video me 1080p available ho.
- Remove background ka first run model download kar sakta hai, isliye pehli baar thoda time lag sakta hai.
- Downloaded files `backend/downloads` me save hote hain.
- Uploaded images temporary source ke roop me `backend/uploads` me save hote hain.
- Naye tools: QR Code Generator, Image Converter, Watermark Studio.
- Video To MP3 me ab URL link aur local video upload dono options hain.
- Remove Background me transparent, white, dark, blue studio background aur edge softness controls hain.
