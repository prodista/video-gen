import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from pydantic import BaseModel

app = FastAPI()

# MongoDB Setup (using Environment Variables for security)
MONGO_URI = os.getenv("MONGODB_URI")
client = MongoClient(MONGO_URI)
db = client['ai_video_db']
tasks_col = db['video_tasks']

class VideoPrompt(BaseModel):
    user: str
    prompt: str

@app.get("/api/history")
async def get_history():
    history = list(tasks_col.find().sort("_id", -1).limit(10))
    # Convert MongoDB ObjectIds to strings for JSON
    clean_history = [{"user": h['user'], "prompt": h['prompt'], "status": h.get('status', 'pending')} for h in history]
    return clean_history

@app.post("/api/generate")
async def generate_video(data: VideoPrompt):
    task = {
        "user": data.user,
        "prompt": data.prompt,
        "status": "processing"
    }
    tasks_col.insert_one(task)
    
    return {"message": "Video generation started!", "prompt": data.prompt}

