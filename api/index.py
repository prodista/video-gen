import os
import json
from google.cloud import storage, aiplatform_client_v1
from google.protobuf import json_format
from google.oauth2 import service_account
from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import vertexai
from vertexai.preview.generative_models import GenerativeModel
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
from bson import ObjectId

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        video_model = GenerativeModel("veo-3.1-lite-generate-001")
        print("✅ Vertex AI & Video Model 초기화 성공")
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")

class VideoRequest(BaseModel):
    prompt: str

client_options = {"api_endpoint": f"{os.environ.get('GCP_LOCATION')}-aiplatform.googleapis.com"}
prediction_client = aiplatform_client_v1.PredictionServiceClient(client_options=client_options)

@app.post("/api/generate-video")
async def generate_video(request: Request):
    try:
        data = await request.json()
        prompt = data.get("prompt")
        room_id = data.get("roomId")
        
        project_id = os.environ.get("GCP_PROJECT_ID")
        location = os.environ.get("GCP_LOCATION")
        bucket_name = os.environ.get("GCP_BUCKET_NAME")

        # 1. 모델 경로 설정
        endpoint = f"projects/{project_id}/locations/{location}/publishers/google/models/veo-3.1-lite-generate-001"

        # 2. 요청 인스턴스 구성
        instance = json_format.ParseDict({
            "prompt": prompt
        }, {})
        
        # 3. 출력 설정 (GCS 버킷으로 바로 저장하도록 지시)
        output_file_prefix = f"videos/{room_id}_{int(time.time())}"
        parameters = json_format.ParseDict({
            "sampleCount": 1,
            "aspectRatio": "16:9",
            "outputGcsUri": f"gs://{bucket_name}/{output_file_prefix}"
        }, {})

        # 4. LRO 요청 실행
        operation = prediction_client.predict_long_running(
            endpoint=endpoint,
            instances=[instance],
            parameters=parameters,
        )

        # 5. DB에는 "생성 중" 상태로 먼저 기록
        temp_msg = {
            "roomId": room_id,
            "senderId": "system_ai",
            "text": "🎬 영상 생성 업무를 접수했습니다! 약 1분 뒤에 확인해주세요.",
            "videoUrl": None, 
            "status": "processing",
            "opName": operation.operation.name, # 나중에 상태 확인용
            "createdAt": datetime.now(KST)
        }
        db.messages.insert_one(temp_msg)

        return JSONResponse(content={"status": "success", "message": "요청 완료"})

    except Exception as e:
        print(f"Veo Error: {str(e)}")
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
async def receive_messages(room_id: str):
    try:
        # MongoDB에서 해당 방의 메시지 가져오기
        messages = list(db.messages.find({"roomId": room_id}).sort("createdAt", 1))
        
        # ObjectId를 문자열로 변환하여 JSON 직렬화 가능하게 만듦
        for msg in messages:
            msg["_id"] = str(msg["_id"])
            if "createdAt" in msg:
                msg["createdAt"] = msg["createdAt"].isoformat()
                
        return JSONResponse(content=messages)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

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
