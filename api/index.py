import os
import datetime
from fastapi import FastAPI
from pymongo import MongoClient

app = FastAPI()

# 몽고DB 연결 (환경변수 사용)
uri = os.environ.get("MONGODB_URI")
client = MongoClient(uri)
db = client['video_gen']

@app.post("/api/onboarding")
async def save_onboarding(data: dict):
    try:
        user_data = {
            "participantId": data.get("participantId"),
            "anxietyFactors": data.get("anxietyFactors"), # 리스트 형태 그대로 저장됨
            "initialAnxiety": int(data.get("initialAnxiety")),
            "timestamp": datetime.datetime.now()
        }
        db.users.insert_one(user_data)
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/history")
async def get_history():
    try:
        # 최신순으로 5개만 가져오기
        data = list(db.history.find({}, {"_id": 0}).sort("_id", -1).limit(5))
        return data
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/generate")
async def save_prompt(data: dict):
    try:
        client = MongoClient(uri)
        db = client['video_gen']
        db.history.insert_one({"user": data.get("user"), "prompt": data.get("prompt")})
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}






