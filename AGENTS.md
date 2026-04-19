# Anime Bingo Real-time

## Commands

### Development
```bash
pip install -r requirements.txt
python app.py
```

### Deployment (Heroku/Render)
```bash
gunicorn --worker-class eventlet -w 1 app:app
```

## Tech Stack
- Backend: Flask + Flask-SocketIO + Eventlet
- Frontend: HTML5 + CSS3 + Vanilla JS + Socket.io Client
- Real-time: WebSocket via Socket.io

## Features
- สุ่มโจทย์ 25 ข้อ (5x5 Grid)
- อัปเดตสถานะแบบ Real-time ทุกคน
- ป้องกันการตอบซ้ำ
- Responsive Design