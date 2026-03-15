from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
import os

app = FastAPI()

# CORS 설정 (프론트엔드 통신 허용)
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

@app.post("/api/user/onboarding")
async def save_user(request: Request):
    try:
        data = await request.json()
        user_doc = {
            "participantId": data.get("participantId"),
            "anxietyFactors": data.get("anxietyFactors"),
            "initialAnxiety": data.get("initialAnxiety"),
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
        return {"status": "error", "message": str(e)}

# Vercel용 핸들러 (FastAPI는 필요 없지만 안전하게 추가)
@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.route("/history", methods=['GET'])
def get_history():
    try:
        # db.history가 아닌 collection 혹은 별도 history 컬렉션 사용 시 수정 필요
        # 여기서는 단순히 users 컬렉션에서 최근 데이터를 가져오는 예시입니다.
        data = list(collection.find({}, {"_id": 0}).sort("_id", -1).limit(10))
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Vercel이 앱을 인식하도록 설정
def handler(event, context):
    return app(event, context)
