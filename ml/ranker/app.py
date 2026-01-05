from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def health():
    return {"status": "ranker is running"}

@app.post("/rank")
def rank():
    # TODO: ランキング処理を実装
    return {"message": "ranking endpoint"}

