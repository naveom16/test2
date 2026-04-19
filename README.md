# Anime Bingo Real-time

เกมบิงโกอนิเมะแบบ real-time multiplayer ที่ใช้ Flask + SocketIO

## Features

- สุ่มโจทย์ 25 ข้อ (5x5 Grid)
- อัปเดตสถานะแบบ Real-time ทุกคน
- ป้องกันการตอบซ้ำ
- Responsive Design
- Persistent player sessions
- Auto-skip disconnected players
- Bingo reset on win/tie/dispute

## Tech Stack

- Backend: Flask + Flask-SocketIO + Eventlet
- Frontend: HTML5 + CSS3 + Vanilla JS + Socket.io Client
- Real-time: WebSocket via Socket.io

## Local Development

```bash
pip install -r requirements.txt
python app.py
```

เปิดเบราว์เซอร์ที่ `http://127.0.0.1:5002`

## Deployment on Render

1. Push code ขึ้น GitHub repository
2. เข้า [Render Dashboard](https://dashboard.render.com)
3. สร้าง New Web Service
4. เชื่อมกับ GitHub repo
5. ตั้งค่า:
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn --worker-class eventlet -w 1 app:app`
6. Deploy!

## Environment Variables

ถ้าต้องการกำหนดพอร์ต:
```bash
PORT=5002 python app.py
```

## Project Structure

```
├── app.py                 # Main Flask app
├── server/
│   ├── event_bus.py       # Event system
│   └── player_session.py  # Session management
├── templates/
│   └── index.html         # Main template
├── static/
│   ├── styles.css         # CSS styles
│   └── app.js             # Client-side JS
├── requirements.txt       # Python dependencies
├── Procfile              # Heroku/Render process file
├── runtime.txt           # Python version
└── README.md             # This file
```