from fastapi import FastAPI
import os
import uvicorn

app = FastAPI()

@app.get("/")
def health():
    return {"status": "ranker is running"}

@app.post("/rank")
def rank():
    # TODO: ランキング処理を実装
    return {"message": "ranking endpoint"}

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
