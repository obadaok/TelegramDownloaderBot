# Telegram Downloader Bot

بوت Telegram احترافي لتحميل الفيديوهات والصوت من YouTube وجميع المنصات المدعومة في yt-dlp.

## المميزات

- تحميل من YouTube, TikTok, Instagram, Facebook, X/Twitter, Reddit, Vimeo, Twitch, SoundCloud, Pinterest, Vimeo وغيرها (1800+ موقع)
- تحميل الفيديو (MP4) والصوت (MP3)
- اختيار الجودة: 360p, 480p, 720p, 1080p, Best
- Redis Queue + Workers + Concurrency
- PostgreSQL / SQLite
- Docker + Render ready
- ffprobe + FFmpeg للدمج والتحويل
- بدون تكرار التحميل (Dedupe)
- تنظيف الملفات المؤقتة
- حدود قابلة للتعديل من Environment
- Progress Updates
- دعم متعدد المنصات

## الأوامر

| الأمر | الوصف |
|---|---|
| /start | بدء المحادثة وطلب اسم |
| /menu | القائمة الرئيسية |
| /help | المساعدة |
| /settings | الإعدادات |
| /name | تغيير الاسم |
| /download | تحميل عام |
| /audio | تحميل صوتي فقط |
| /video | تحميل فيديو |
| /queue | قائمة الانتظار |
| /status | حالة التحميلات |
| /cancel | إلغاء مهمة |
| /history | السجل |
| /clear | مسح السجل |
| /about | معلومات البوت |

## التثبيت

### محلي
```bash
git clone https://github.com/username/TelegramDownloaderBot.git
cd TelegramDownloaderBot
cp .env.example .env
# Edit .env with your values
pip install -r requirements.txt
python main.py
```

### Docker
```bash
docker-compose up -d
```

### Render
- ارفع المشروع على GitHub
- اربط بـ Render
- استخدم `render.yaml` للنشر التلقائي
- أضف الـ secrets في Render Dashboard

## Environment Variables

راجع `.env.example` للقائمة الكاملة.

## الترخيص

MIT
