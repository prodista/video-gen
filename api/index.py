import os
import json
from google.cloud import storage
from google.oauth2 import service_account
from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import vertexai
from vertexai.generative_models import GenerativeModel
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
from bson import ObjectId

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = FastAPI()

KST = timezone(timedelta(hours=9))

# 환경 변수 가져오기
sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
project_id = os.environ.get("GCP_PROJECT_ID")
location = os.environ.get("GCP_LOCATION", "us-central1")
bucket_name = os.environ.get("GCP_BUCKET_NAME") # GCS 버킷 이름 환경변수

video_model = None
storage_client = None

if sa_json:
    try:
        sa_info = json.loads(sa_json)
        credentials = service_account.Credentials.from_service_account_info(sa_info)
        
        # Vertex AI 초기화
        vertexai.init(project=project_id, location=location, credentials=credentials)
        # GCS 클라이언트 초기화
        storage_client = storage.Client(credentials=credentials, project=project_id)
        
        # 모델 정의 (변수명: video_model)
        video_model = GenerativeModel("veo-3.1-lite-preview-0502")
        print("✅ Vertex AI & Video Model 초기화 성공")
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")

class VideoRequest(BaseModel):
    prompt: str

@app.post("/api/generate-video")
async def generate_video(request: Request):
    global video_model, storage_client
    
    if not video_model:
        raise HTTPException(status_code=500, detail="서버 모델이 준비되지 않았습니다.")

    try:
        data = await request.json()
        prompt = data.get("prompt")
        room_id = data.get("roomId")
        p_id = data.get("pId")

        if not prompt:
            raise HTTPException(status_code=400, detail="프롬프트가 없습니다.")

        # [STEP 1] 영상 생성 요청 (Veo 모델 호출)
        response = video_model.generate_content(prompt) 
        
        # [STEP 2] 생성된 바이너리 데이터 추출 (SDK 구조에 따라 다름)
        video_bytes = response.candidates[0].content.parts[0].inline_data.data
        
        # [STEP 3] GCS에 업로드
        file_name = f"video_{room_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
        blob = storage_client.bucket(bucket_name).blob(f"generated_videos/{file_name}")
        
        blob.upload_from_string(video_bytes, content_type='video/mp4')
        video_url = blob.public_url # 공개 URL 생성

        # [STEP 4] DB에 메시지 저장 (유저에게 보여주기 위함)
        video_message = {
            "roomId": room_id,
            "senderId": "system_ai",
            "text": f"🎬 생성된 영상: {prompt}",
            "videoUrl": video_url,
            "createdAt": datetime.now(KST),
            "type": "video"
        }
        db.messages.insert_one(video_message)

        return JSONResponse(content={
            "status": "success",
            "videoUrl": video_url,
            "message": "영상이 성공적으로 생성되었습니다."
        })

    except Exception as e:
        print(f"❌ 영상 생성 오류: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})
        
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
