from fastapi import FastAPI

app = FastAPI(title="bud")


@app.get("/")
async def root():
    return {"status": "ok"}
