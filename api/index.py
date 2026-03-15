from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.get("/history")
async def get_history():
    try:
        data = list(collection.find({}, {"_id": 0}).sort("_id", -1).limit(10))
        return data
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def read_root():
    return {"Hello": "World"}
