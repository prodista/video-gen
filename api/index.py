from fastapi import FastAPI, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
import os
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url

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

# Cloudinary 연결
cloudinary.config( 
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
  api_key = os.getenv("CLOUDINARY_API_KEY"),
  api_secret = os.getenv("CLOUDINARY_API_SECRET")
)

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "FastAPI is running"}

@app.post("/api/room/check")
async def check_room(request: Request):
    data = await request.json()
    room_id = data.get("roomId")
    input_pw = data.get("password")
    
    # DB에서 해당 방 정보를 찾음
    room = db['rooms'].find_one({"roomId": room_id})
    
    if not room:
        # 방이 없으면 새로 생성 (처음 들어온 유저가 비번 결정)
        db['rooms'].insert_one({"roomId": room_id, "password": input_pw})
        return {"status": "created", "message": "새로운 방이 생성되었습니다."}
    else:
        # 방이 있으면 비번 비교
        if room['password'] == input_pw:
            return {"status": "success", "message": "입장 성공"}
        else:
            return JSONResponse(status_code=401, content={"status": "fail", "message": "비밀번호가 틀립니다."})

# 로그인/조회 (HTML의 fetch('/api/user/${pId}')와 매칭)
@app.get("/api/user/{participant_id}")
async def get_user(participant_id: str):
    user = collection.find_one({"participantId": participant_id}, {"_id": 0})
    if user:
        return user
    else:
        return JSONResponse(status_code=404, content={"message": "User not found"})

# 영상 URL 업데이트 (HTML의 fetch('/api/user/update-video')와 매칭)
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

# 채팅 메시지 보내기
@app.post("/api/chat/send")
async def send_message(request: Request):
    data = await request.json()
    # 여기서 전해받은 데이터를 MongoDB에 넣음
    db['messages'].insert_one(data)
    return {"status": "success"}

# 채팅 메시지 리스트 가져오기 (폴링용)
@app.get("/api/chat/receive/{room_id}")
async def get_messages(room_id: str):
    try:
        # 해당 방의 메시지들을 시간순(오름차순)으로 정렬하여 50개 가져옴
        messages = list(db['messages'].find({"roomId": room_id}).sort("timestamp", 1).limit(50))
        for msg in messages:
            msg["_id"] = str(msg["_id"]) # JSON 변환을 위해 문자열로 변경
        return messages
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/user/profile-image")
async def upload_profile_image(participantId: str, file: UploadFile = File(...)):
    try:
        # Cloudinary에 이미지 업로드 (프로필용으로 크기 조절/최적화)
        upload_result = cloudinary.uploader.upload(
            file.file,
            folder = "profiles",
            transformation = [
                {"width": 200, "height": 200, "crop": "thumb", "gravity": "face"}, # 얼굴 중심으로 자르기
                {"quality": "auto", "fetch_format": "auto"}
            ]
        )
        
        img_url = upload_result['secure_url']

        # MongoDB에서 해당 사용자의 프로필 URL 업데이트
        await db.users.update_one(
            {"participantId": participantId},
            {"$set": {"profileImg": img_url}},
            upsert=True
        )
        
        return {"status": "success", "profileImg": img_url}
    except Exception as e:
        return {"status": "error", "message": str(e)}
