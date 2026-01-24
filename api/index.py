import os
from fastapi import FastAPI
from pymongo import MongoClient

app = FastAPI()

@app.get("/api/history")
async def get_history():
    # Calling it INSIDE the function forces Vercel to look for it NOW
    uri = os.environ.get("MONGODB_URI") 
    
    if not uri:
        return {"error": "Still missing. Check Vercel 'Production' checkbox."}
    
    try:
        client = MongoClient(uri)
        db = client['video_gen']
        history = list(db.history.find({}, {"_id": 0}))
        return history
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



