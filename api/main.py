from fastapi import FastAPI, HTTPException
from data.integration_service import IntegrationService
from pydantic import BaseModel
from typing import Dict, Any

app = FastAPI(title="ClashZero API")
service = IntegrationService()

class TimetableRequest(BaseModel):
    academic_year: str

@app.get("/")
def read_root():
    return {"message": "Welcome to ClashZero API"}

@app.post("/generate")
def generate_timetable(request: TimetableRequest):
    try:
        result = service.generate_timetable(request.academic_year)
        if result["status"] == "success":
            return result["data"]
        else:
            raise HTTPException(status_code=500, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
