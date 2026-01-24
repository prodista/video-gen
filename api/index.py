import os
from fastapi import FastAPI, Body
from pymongo import MongoClient

app = FastAPI()

uri = os.getenv("MONGODB_URI")
client = MongoClient(uri)
db = client['video_gen']
history_col = db['history']

@app.get("/api/history")
async def get_history():
    # Fetch last 10 entries from MongoDB
    cursor = history_col.find({}, {"_id": 0}).sort("_id", -1).limit(10)
    return list(cursor)

@app.post("/api/generate")
async def save_prompt(data: dict = Body(...)):
    # Save the user request to MongoDB
    history_col.insert_one({
        "user": data.get("user"),
        "prompt": data.get("prompt"),
        "status": "pending"
    })
    return {"status": "success"}




