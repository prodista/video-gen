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
    try:
        data = request.json
        print("수신 데이터:", data) # Vercel 로그 확인용
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400

        user_doc = {
            "participantId": data.get("participantId"),
            "anxietyFactors": data.get("anxietyFactors"),
            "initialAnxiety": data.get("initialAnxiety"),
            "purpose": data.get("purpose"),
            "videoUrl": data.get("videoUrl", ""), # 기존 URL 유지 혹은 빈값
            "createdAt": data.get("createdAt")
        }
        
        # participantId가 이미 있다면 업데이트, 없으면 새로 삽입 (Upsert)
        result = collection.update_one(
            {"participantId": user_doc["participantId"]},
            {"$set": user_doc},
            upsert=True
        )
        return jsonify({"status": "success", "inserted_id": str(result.upserted_id)}), 200
    
    except Exception as e:
        print("에러 발생:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/user/update-video', methods=['POST'])
def update_video():
    try:
        data = request.json
        p_id = data.get("participantId")
        v_url = data.get("videoUrl")

        collection.update_one(
            {"participantId": p_id},
            {"$set": {"videoUrl": v_url}}
        )
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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
