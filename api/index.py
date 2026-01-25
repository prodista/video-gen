import os
import datetime
from fastapi import FastAPI
from pymongo import MongoClient

app = FastAPI()

# MongoDB 연결 환경변수
uri = os.environ.get("MONGODB_URI")
client = MongoClient(uri)
db = client['video_gen']

@app.get("/api/user/{participant_id}")
async def get_user(participant_id: str):
    try:
        # 데이터베이스에서 해당 ID 찾기
        user = db.users.find_one({"participantId": participant_id}, {"_id": 0})
        
        if user:
            # 몽고DB의 datetime 객체는 JSON으로 바로 안 넘어가므로 문자열로 변환 (중요!)
            if "createdAt" in user:
                user["createdAt"] = user["createdAt"].isoformat()
            if "timestamp" in user:
                user["timestamp"] = user["timestamp"].isoformat()
                
            return user
        else:
            return JSONResponse(status_code=404, content={"error": "User not found"})
    except Exception as e:
        print(f"Login Error: {e}") # 서버 터미널에서 에러 확인용
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/onboarding")
async def save_onboarding(data: dict):
    try:
        # 프론트엔드 변수명에 맞춰 데이터 추출
        user_profile = {
            "participantId": data.get("participantId"),
            "anxietyFactors": data.get("anxietyFactors"), # 리스트 형태 [ "직장", "미래" ]
            "initialAnxiety": int(data.get("initialAnxiety")),
            "purpose": data.get("purpose"),
            "createdAt": datetime.datetime.now()
        }
        
        # 'users' 컬렉션에 저장
        db.users.insert_one(user_profile)
        return {"status": "success"}
        
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}, 500

@app.get("/api/history")
async def get_history():
    try:
        # 기존 영상 히스토리 로드 (필요시 사용)
        data = list(db.history.find({}, {"_id": 0}).sort("_id", -1).limit(10))
        return data
    except Exception as e:
        return {"error": str(e)}


