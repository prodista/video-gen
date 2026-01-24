import os
from fastapi import FastAPI
from pymongo import MongoClient
import pymongo

app = FastAPI()

# 1. MAKE SURE THIS MATCHES YOUR VERCEL KEY EXACTLY
uri = os.getenv("MONGODB_URI") 

@app.get("/api/history")
async def get_history():
    if not uri:
        return {"error": "Vercel Environment Variable 'MONGODB_URI' is missing!"}
    
    try:
        # 2. We add a timeout so it doesn't spin forever
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        db = client['ai_video_app']
        history_col = db['history']
        
        # Test the connection immediately
        client.admin.command('ping')
        
        data = list(history_col.find({}, {"_id": 0}).limit(10))
        return data
    
    except pymongo.errors.ConfigurationError as e:
        return {"error": f"Configuration Error: {str(e)}. Check your URI format."}
    except pymongo.errors.OperationFailure as e:
        return {"error": f"Auth Error: {str(e)}. Your MongoDB password or username is likely wrong."}
    except Exception as e:
        return {"error": f"General Error: {str(e)}"}

@app.post("/api/generate")
async def save_prompt(data: dict):
    try:
        client = MongoClient(uri)
        db = client['ai_video_app']
        db.history.insert_one({"user": data.get("user"), "prompt": data.get("prompt")})
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}
