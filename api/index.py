from flask import Flask, request, jsonify
from pymongo import MongoClient
import os

app = Flask(__name__)

# Vercel 환경 변수에서 가져오기
MONGO_URI = os.environ.get("MONGODB_URI")
client = MongoClient(MONGO_URI)
db = client['video_gen'] # 데이터베이스 이름
collection = db['users']   # 컬렉션 이름

@app.route('/user/onboarding', methods=['POST'])
def save_user():
data = request.json

# 데이터 구조 정의 (HTML에서 보낸 키값과 일치해야 함)
user_doc = {
    "participantId": data.get("participantId"),
    "anxietyFactors": data.get("anxietyFactors"),
    "initialAnxiety": data.get("initialAnxiety"),
    "purpose": data.get("purpose"),
    "videoUrl": "", # 처음엔 빈값으로 생성
    "createdAt": data.get("createdAt")
}

# participantId가 이미 있다면 업데이트, 없으면 새로 삽입 (Upsert)
collection.update_one(
    {"participantId": user_doc["participantId"]},
    {"$set": user_doc},
    upsert=True
)
return jsonify({"status": "success", "message": "Data saved"}), 200

# 영상 URL만 따로 업데이트하는 API (나중에 영상 생성 후 호출)
@app.route('/user/update-video', methods=['POST'])
def update_video():
data = request.json
p_id = data.get("participantId")
v_url = data.get("videoUrl")

collection.update_one(
    {"participantId": p_id},
    {"$set": {"videoUrl": v_url}}
)
return jsonify({"status": "success"}), 200

# Vercel이 앱을 인식하도록 설정
def handler(event, context):
return app(event, context)

@app.route('/user/onboarding', methods=['POST'])
def save_user():
    try:
        data = request.json
        print("수신 데이터:", data) # Vercel 로그에 찍힙니다.
        
        user_doc = {
            "participantId": data.get("participantId"),
            "anxietyFactors": data.get("anxietyFactors"),
            "initialAnxiety": data.get("initialAnxiety"),
            "purpose": data.get("purpose"),
            "videoUrl": "",
            "createdAt": data.get("createdAt")
        }
        
        # 실제 DB 작업
        result = collection.update_one(
            {"participantId": user_doc["participantId"]},
            {"$set": user_doc},
            upsert=True
        )
        return jsonify({"status": "success", "inserted_id": str(result.upserted_id)}), 200
    
    except Exception as e:
        print("에러 발생:", str(e)) # 로그에서 에러 원인 확인 가능
        return jsonify({"status": "error", "message": str(e)}), 500

@app.get("/history")
async def get_history():
try:
    # 기존 영상 히스토리 로드 (필요시 사용)
    data = list(db.history.find({}, {"_id": 0}).sort("_id", -1).limit(10))
    return data
except Exception as e:
    return {"error": str(e)}





