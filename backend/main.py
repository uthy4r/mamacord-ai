import base64
import io
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal, Optional

from rag import retrieve_context
from triage import run_triage, extract_uss_fields
from handover import generate_handover_note
from download import generate_pdf, generate_docx
from database import init_db, get_db
from auth import router as auth_router, get_current_user
from models import User, TriageRecord

load_dotenv()

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("mamacord")

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CORS — must be registered FIRST so it wraps everything including error responses
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://mamacord-ai.vercel.app,http://localhost:5173,http://localhost:4173",
).split(",")

# ---------------------------------------------------------------------------
# App lifespan — initialise DB tables on startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        logger.info("database_ready | tables initialised")
    except Exception as e:
        logger.warning("database_unavailable | %s — auth/history endpoints will fail until DB is reachable", type(e).__name__)
    yield


app = FastAPI(title="Mamacord AI", docs_url=None, redoc_url=None, lifespan=lifespan)

# CORS is added immediately after app creation — before any routers or exception handlers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(auth_router)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_USS_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
VALID_URINE_PROTEIN = {"negative", "trace", "1+", "2+", "3+"}
VALID_URINE_GLUCOSE = {"negative", "trace", "positive"}
VALID_PLACENTAL = {"normal", "low-lying", "praevia"}
VALID_PRESENTATION = {"cephalic", "breech", "transverse"}
VALID_LIQUOR = {"normal", "reduced", "oligohydramnios", "increased"}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class TriageInput(BaseModel):
    # Patient details
    patient_id: Optional[str] = None
    age: int
    gestational_age: int
    gravida: Optional[int] = None
    para: Optional[int] = None

    # Vitals
    systolic_bp: float
    diastolic_bp: float
    temperature: float
    heart_rate: float

    # Labs
    pcv: float                  # Packed Cell Volume in % (replaces Hb)
    urine_protein: str
    urine_glucose: str

    # FBC (optional — for sepsis screening)
    wbc: Optional[float] = None         # x10³/μL
    neutrophils: Optional[float] = None  # %
    platelets: Optional[int] = None      # x10³/μL

    # USS (optional)
    placental_location: Optional[str] = None
    fetal_presentation: Optional[str] = None
    liquor_volume: Optional[str] = None
    fhr: Optional[float] = None
    uss_image_base64: Optional[str] = None  # base64-encoded USS image

    @field_validator("systolic_bp", "diastolic_bp", "temperature", "heart_rate", "pcv", mode="before")
    @classmethod
    def cast_to_float(cls, v):
        return float(v)

    @field_validator("age", "gestational_age", mode="before")
    @classmethod
    def cast_to_int(cls, v):
        return int(v)

    @field_validator("age")
    @classmethod
    def validate_age(cls, v):
        if not (10 <= v <= 60):
            raise ValueError("Age must be between 10 and 60 years")
        return v

    @field_validator("gestational_age")
    @classmethod
    def validate_gestational_age(cls, v):
        if not (1 <= v <= 45):
            raise ValueError("Gestational age must be between 1 and 45 weeks")
        return v

    @field_validator("systolic_bp")
    @classmethod
    def validate_systolic(cls, v):
        if not (50 <= v <= 300):
            raise ValueError("Systolic BP must be between 50 and 300 mmHg")
        return v

    @field_validator("diastolic_bp")
    @classmethod
    def validate_diastolic(cls, v):
        if not (30 <= v <= 200):
            raise ValueError("Diastolic BP must be between 30 and 200 mmHg")
        return v

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v):
        if not (33.0 <= v <= 42.0):
            raise ValueError("Temperature must be between 33.0 and 42.0°C")
        return v

    @field_validator("heart_rate")
    @classmethod
    def validate_heart_rate(cls, v):
        if not (30 <= v <= 250):
            raise ValueError("Heart rate must be between 30 and 250 bpm")
        return v

    @field_validator("pcv")
    @classmethod
    def validate_pcv(cls, v):
        if not (5 <= v <= 70):
            raise ValueError("PCV must be between 5% and 70%")
        return v

    @field_validator("urine_protein")
    @classmethod
    def validate_urine_protein(cls, v):
        if v.lower() not in VALID_URINE_PROTEIN:
            raise ValueError(f"Urine protein must be one of: {', '.join(sorted(VALID_URINE_PROTEIN))}")
        return v

    @field_validator("urine_glucose")
    @classmethod
    def validate_urine_glucose(cls, v):
        if v.lower() not in VALID_URINE_GLUCOSE:
            raise ValueError(f"Urine glucose must be one of: {', '.join(sorted(VALID_URINE_GLUCOSE))}")
        return v

    @field_validator("placental_location")
    @classmethod
    def validate_placental(cls, v):
        if v is not None and v.lower() not in VALID_PLACENTAL:
            raise ValueError(f"Placental location must be one of: {', '.join(sorted(VALID_PLACENTAL))}")
        return v

    @field_validator("fetal_presentation")
    @classmethod
    def validate_presentation(cls, v):
        if v is not None and v.lower() not in VALID_PRESENTATION:
            raise ValueError(f"Fetal presentation must be one of: {', '.join(sorted(VALID_PRESENTATION))}")
        return v

    @field_validator("liquor_volume")
    @classmethod
    def validate_liquor(cls, v):
        if v is not None and v.lower() not in VALID_LIQUOR:
            raise ValueError(f"Liquor volume must be one of: {', '.join(sorted(VALID_LIQUOR))}")
        return v

    @field_validator("fhr")
    @classmethod
    def validate_fhr(cls, v):
        if v is not None and not (50 <= v <= 250):
            raise ValueError("FHR must be between 50 and 250 bpm")
        return v

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v):
        if v is not None and len(v) > 50:
            raise ValueError("Patient ID must be 50 characters or fewer")
        return v

    @field_validator("uss_image_base64")
    @classmethod
    def validate_uss_image(cls, v):
        if v is None:
            return v
        try:
            raw = base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("USS image must be valid base64")
        if len(raw) > MAX_USS_IMAGE_BYTES:
            raise ValueError(f"USS image must be smaller than {MAX_USS_IMAGE_BYTES // (1024*1024)} MB")
        # Check magic bytes for JPEG / PNG
        if not (raw[:2] == b"\xff\xd8" or raw[:4] == b"\x89PNG"):
            raise ValueError("USS image must be a JPEG or PNG file")
        return v

    @field_validator("wbc")
    @classmethod
    def validate_wbc(cls, v):
        if v is not None and not (0.1 <= v <= 100):
            raise ValueError("WBC must be between 0.1 and 100 x10³/μL")
        return v

    @field_validator("neutrophils")
    @classmethod
    def validate_neutrophils(cls, v):
        if v is not None and not (0 <= v <= 100):
            raise ValueError("Neutrophils must be between 0 and 100%")
        return v

    @field_validator("platelets")
    @classmethod
    def validate_platelets(cls, v):
        if v is not None and not (1 <= v <= 1000):
            raise ValueError("Platelets must be between 1 and 1000 x10³/μL")
        return v


class DownloadPayload(BaseModel):
    format: Literal["pdf", "docx"]
    result: dict
    input: dict


@app.get("/")
def root():
    return {"app": "Mamacord AI", "docs": "API is running. Use the frontend client."}


@app.get("/health")
@limiter.limit("30/minute")
def health_check(request: Request):
    return {"status": "ok", "app": "Mamacord AI"}


class UssAnalyzeRequest(BaseModel):
    image_base64: str


@app.post("/api/uss-analyze")
@limiter.limit("10/minute")
async def uss_analyze(body: UssAnalyzeRequest, request: Request):
    """Analyze a USS image and return structured findings to pre-fill form fields."""
    request_id = uuid.uuid4().hex[:12]
    logger.info("uss_analyze_start | request_id=%s", request_id)
    try:
        # Validate image size
        raw = base64.b64decode(body.image_base64, validate=True)
        if len(raw) > MAX_USS_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Image exceeds 5 MB limit")
        result = await extract_uss_fields(body.image_base64)
        logger.info("uss_analyze_complete | request_id=%s", request_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("uss_analyze_error | request_id=%s | error=%s", request_id, type(e).__name__)
        return {
            "placental_location": None,
            "fetal_presentation": None,
            "liquor_volume": None,
            "fhr": None,
            "summary": "USS analysis failed. Please enter findings manually.",
        }


@app.post("/api/triage")
@limiter.limit("10/minute")
async def triage(
    data: TriageInput,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_id = uuid.uuid4().hex[:12]
    start = time.monotonic()
    logger.info(
        "triage_start | request_id=%s | user=%s | patient_id=%s | age=%s | ga=%s | bp=%s/%s",
        request_id,
        str(user.id)[:8],
        data.patient_id or "anon",
        data.age,
        data.gestational_age,
        data.systolic_bp,
        data.diastolic_bp,
    )
    try:
        context = retrieve_context(data)
        result = await run_triage(data, context)

        handover_note = None
        if result.get("risk_level") == "RED":
            handover_note = generate_handover_note(data, result)

        # Persist triage record
        record = TriageRecord(
            user_id=user.id,
            patient_id=data.patient_id,
            age=data.age,
            gestational_age=data.gestational_age,
            systolic_bp=data.systolic_bp,
            diastolic_bp=data.diastolic_bp,
            risk_level=result.get("risk_level", "UNKNOWN"),
            primary_concern=result.get("primary_concern"),
            recommended_action=result.get("recommended_action"),
        )
        db.add(record)
        await db.commit()

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "triage_complete | request_id=%s | risk=%s | concern=%s | flags=%d | duration_ms=%d",
            request_id,
            result.get("risk_level"),
            result.get("primary_concern", "")[:80],
            len(result.get("flags", [])),
            duration_ms,
        )

        return {
            "risk_level": result.get("risk_level"),
            "primary_concern": result.get("primary_concern"),
            "flags": result.get("flags", []),
            "rationale": result.get("rationale"),
            "citations": result.get("citations", []),
            "recommended_action": result.get("recommended_action"),
            "handover_note": handover_note,
        }
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(
            "triage_error | request_id=%s | error=%s | duration_ms=%d",
            request_id,
            type(e).__name__,
            duration_ms,
        )
        raise HTTPException(status_code=500, detail="Triage processing failed. Please try again.")


@app.post("/api/download")
@limiter.limit("10/minute")
async def download_report(payload: DownloadPayload, request: Request):
    request_id = uuid.uuid4().hex[:12]
    logger.info("download_start | request_id=%s | format=%s", request_id, payload.format)
    try:
        fmt = payload.format.lower()
        if fmt == "pdf":
            content = generate_pdf(payload.input, payload.result)
            logger.info("download_complete | request_id=%s | format=pdf | bytes=%d", request_id, len(content))
            return StreamingResponse(
                io.BytesIO(content),
                media_type="application/pdf",
                headers={"Content-Disposition": "attachment; filename=mamacord-triage-report.pdf"},
            )
        elif fmt == "docx":
            content = generate_docx(payload.input, payload.result)
            logger.info("download_complete | request_id=%s | format=docx | bytes=%d", request_id, len(content))
            return StreamingResponse(
                io.BytesIO(content),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": "attachment; filename=mamacord-triage-report.docx"},
            )
        else:
            raise HTTPException(status_code=400, detail="Format must be 'pdf' or 'docx'")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("download_error | request_id=%s | error=%s", request_id, type(e).__name__)
        raise HTTPException(status_code=500, detail="Report generation failed. Please try again.")


# ---------------------------------------------------------------------------
# Global exception handler — never leak internal details
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_error | path=%s | error=%s", request.url.path, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "An internal error occurred."})
