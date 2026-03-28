from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import MongoClient
import os

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB 연결
MONGO_URI = os.environ.get("MONGODB_URI")
client = MongoClient(MONGO_URI)
db = client['video_gen']
collection = db['users']

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "FastAPI is running"}

# 1. 로그인/조회 (HTML의 fetch('/api/user/${pId}')와 매칭)
@app.get("/api/user/{participant_id}")
async def get_user(participant_id: str):
    user = collection.find_one({"participantId": participant_id}, {"_id": 0})
    if user:
        return user
    else:
        return JSONResponse(status_code=404, content={"message": "User not found"})

# 2. 온보딩 저장 (HTML의 fetch('/api/user/onboarding')와 매칭)
@app.post("/api/user/onboarding")
async def save_user(request: Request):
    try:
        data = await request.json()
        user_doc = {
            "participantId": data.get("participantId"),
            "anxietyFactors": data.get("anxietyFactors"),
            "initialAnxiety": int(data.get("initialAnxiety", 5)),
            "purpose": data.get("purpose"),
            "videoUrl": "",
            "createdAt": data.get("createdAt")
        }
        collection.update_one(
            {"participantId": user_doc["participantId"]},
            {"$set": user_doc},
            upsert=True
        )
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# 3. 영상 URL 업데이트 (HTML의 fetch('/api/user/update-video')와 매칭)
@app.post("/api/user/update-video")
async def update_video(request: Request):
    try:
        data = await request.json()
        p_id = data.get("participantId")
        v_url = data.get("videoUrl")
        
        collection.update_one(
            {"participantId": p_id},
            {"$set": {"videoUrl": v_url}}
        )
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# 히스토리 불러오기
@app.get("/api/history")
async def get_history():
    try:
        data = list(collection.find({}, {"_id": 0}).sort("_id", -1).limit(10))
        return data
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/")
def read_root():
    return {"Hello": "World"}

# 메시지 보내기
@app.post("/api/chat/send")
async def send_message(request: Request):
    data = await request.json()
    message_doc = {
        "roomId": data.get("roomId"),
        "senderId": data.get("senderId"),
        "text": data.get("text"),
        "timestamp": datetime.utcnow()
    }
    db['messages'].insert_one(message_doc)
    return {"status": "success"}

# 메시지 가져오기
@app.get("/api/chat/receive/{room_id}")
async def get_messages(room_id: str):
    # 최신 메시지 50개 가져오기
    messages = list(db['messages'].find({"roomId": room_id}).sort("timestamp", 1))
    for msg in messages:
        msg["_id"] = str(msg["_id"]) # ObjectId를 문자열로 변환
    return messages
