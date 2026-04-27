import os
import json
from google.cloud import storage
from google.oauth2 import service_account
from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import vertexai
from vertexai.preview.vision_models import VideoGenerationModel
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
from bson import ObjectId

app = FastAPI()

KST = timezone(timedelta(hours=9))

# 환경 변수 가져오기
service_account_info = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
project_id = os.getenv("GCP_PROJECT_ID")
location = os.getenv("GCP_LOCATION", "us-central1")

if service_account_info:
    # 문자열로 들어온 JSON을 사전(dict) 객체로 변환
    info = json.loads(service_account_info)
    credentials = service_account.Credentials.from_service_account_info(info)
    
    # Vertex AI 초기화
    vertexai.init(project=project_id, location=location, credentials=credentials)
else:
    print("CRITICAL: GCP_SERVICE_ACCOUNT_JSON is missing!")

class VideoRequest(BaseModel):
    prompt: str

@app.post("/api/generate-video")
async def generate_video(request: VideoRequest):
    try:
        # Veo 모델에 영상 생성 요청
        # 실제 환경에서는 비동기 작업(Job)으로 처리하고 ID를 반환하는 것이 좋습니다.
        job = model.generate_video(
            prompt=request.prompt,
            # lite 모델의 해상도 및 프레임 설정
            video_capability="generation",
            aspect_ratio="16:9"
        )
        
        # 영상 생성 완료 대기 (Vercel Pro 플랜 이상 권장)
        result = job.result()
        video_uri = result.video.uri # GCS URI 반환
        
        return {"status": "success", "video_url": video_uri}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB 연결
MONGO_URI = os.environ.get("MONGODB_URI")
mongo_client = MongoClient(MONGO_URI) # 변수명 client 중복 방지를 위해 mongo_client로 변경
db = mongo_client['video_gen']

# --- GCS 설정 부분 ---
def get_gcs_client():
    key_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if key_json:
        credentials_info = json.loads(key_json)
        return storage.Client.from_service_account_info(credentials_info)
    return storage.Client()

storage_client = get_gcs_client()
bucket = storage_client.bucket("video-gen-chat")

# --- API 엔드포인트 ---

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "FastAPI is running"}

@app.post("/api/room/check")
async def check_room(request: Request):
    data = await request.json()
    room_id = data.get("roomId")
    input_pw = data.get("password")
    
    room = db['rooms'].find_one({"roomId": room_id})
    
    if not room:
        db['rooms'].insert_one({"roomId": room_id, "password": input_pw})
        return {"status": "created", "message": "새로운 방이 생성되었습니다."}
    else:
        if room['password'] == input_pw:
            return {"status": "success", "message": "입장 성공"}
        else:
            return JSONResponse(status_code=401, content={"status": "fail", "message": "비밀번호가 틀립니다."})

# 로그인/조회
@app.get("/api/user/{participant_id}")
async def get_user(participant_id: str):
    user = db['users'].find_one({"participantId": participant_id}, {"_id": 0})
    if user:
        return user
    else:
        return JSONResponse(status_code=404, content={"message": "User not found"})

# 영상 요청 시 timestamp로 기록
@app.post("/api/user/update-video")
async def update_video(data: dict):
    try:
        p_id = data.get("participantId")
        msg_id = data.get("sourceMsgId")
        text = data.get("promptText")
        
        db.video_requests.insert_one({
            "participantId": p_id,
            "sourceMsgId": msg_id,
            "promptText": text,
            "status": "pending",
            "timestamp": datetime.now() # createdAt -> timestamp로 변경
        })
        
        return {"status": "success", "message": "기록 완료"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 채팅 메시지 보내기
@app.post("/api/chat/send")
async def send_message(request: Request):
    data = await request.json()
    # 클라이언트가 보낸 시간 대신 서버의 정확한 시간을 timestamp로 저장
    data["timestamp"] = datetime.now(KST).isoformat()
    db['messages'].insert_one(data)
    return {"status": "success"}

# 채팅 메시지 리스트 가져오기
@app.get("/api/chat/receive/{room_id}")
async def get_messages(room_id: str):
    try:
        # timestamp 필드를 기준으로 오름차순 정렬
        messages = list(db['messages'].find({"roomId": room_id}).sort("timestamp", 1).limit(100))
        for msg in messages:
            msg["_id"] = str(msg["_id"])
            # datetime 객체를 ISO 포맷 문자열로 변환 (프론트엔드 Date 객체 대응)
            if "timestamp" in msg and isinstance(msg["timestamp"], datetime):
                msg["timestamp"] = msg["timestamp"].astimezone(KST).isoformat()
        return messages
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# 프로필 이미지 업로드
@app.post("/api/user/profile-image")
async def upload_profile_image(participantId: str, file: UploadFile = File(...)):
    try:
        ext = file.filename.split(".")[-1]
        filename = f"profile_{participantId}.{ext}"
        
        blob = bucket.blob(f"profiles/{filename}")
        blob.upload_from_file(file.file, content_type=file.content_type)
        try:
            blob.make_public()
        except:
            pass
        
        # 수동으로 공개 URL 생성 (버킷 이름과 파일 경로 조합)
        img_url = f"https://storage.googleapis.com/{bucket.name}/profiles/{filename}"
        
        # DB에 저장
        db.users.update_one(
            {"participantId": participantId},
            {"$set": {"profileImg": img_url}}, 
            upsert=True
        )
        
        return {"status": "success", "profileImg": img_url}
        
    except Exception as e:
        print(f"Upload Error: {str(e)}") # 서버 로그 확인용
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
        
# 영상 업로드 함수 (내부 로직용)
async def upload_video_to_gcs(local_path, room_id, sender_id):
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"video_{timestamp_str}_{sender_id}.mp4"
    blob = bucket.blob(f"rooms/{room_id}/{filename}")
    blob.upload_from_filename(local_path)
    blob.make_public()
    return blob.public_url
