import os
import tempfile
import logging
import asyncio
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("elevator-transcriber")

app = FastAPI()

# CORS config 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    client = Groq(api_key=os.environ.get("GROQ_API_KEY", "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"))
    logger.info("Groq client initialized successfully")
except Exception as e:
    logger.exception("Failed to initialize Groq client")
    raise RuntimeError(f"Groq client initialization failed: {e}")

# Elevator TCP config
ELEVATOR_HOST = os.environ.get("ELEVATOR_HOST", "172.17.200.236")
ELEVATOR_PORT = int(os.environ.get("ELEVATOR_PORT", "9999"))
TCP_READ_TIMEOUT = 5.0


class TranscribeResponse(BaseModel):
    transcription: str
    floor_number: Optional[int]
    message: str
    tcp_status: Optional[str] = None
    elevator_reply: Optional[str] = None


async def send_floor_to_elevator_async(
    floor_number: int,
    host: str = ELEVATOR_HOST,
    port: int = ELEVATOR_PORT,
    timeout: float = TCP_READ_TIMEOUT,
) -> tuple[str, Optional[str]]:
    """
    Connects to elevator TCP server asynchronously and sends floor number.
    Returns tuple: (status string, elevator reply or None)
    """
    reader = writer = None
    try:
        logger.info(f"Connecting to elevator {host}:{port}")
        reader, writer = await asyncio.open_connection(host, port)
        logger.info("Connected to elevator")

        # Read possible welcome message
        welcome = None
        try:
            welcome_bytes = await asyncio.wait_for(reader.read(1024), timeout=timeout)
            welcome = welcome_bytes.decode(errors="ignore").strip() if welcome_bytes else None
            if welcome:
                logger.info(f"Received welcome message: {welcome}")
        except asyncio.TimeoutError:
            logger.debug("No welcome message received within timeout")

        # Send floor number followed by newline
        payload = f"{floor_number}\n".encode()
        writer.write(payload)
        await writer.drain()
        logger.info(f"Sent floor number {floor_number} to elevator")

        # Await elevator reply (if any)
        elevator_reply = None
        try:
            data = await asyncio.wait_for(reader.read(1024), timeout=timeout)
            if data:
                elevator_reply = data.decode(errors="ignore").strip()
                logger.info(f"Elevator replied: {elevator_reply}")
        except asyncio.TimeoutError:
            logger.debug("No reply from elevator within timeout")

        return "sent", elevator_reply or welcome

    except Exception as e:
        logger.exception(f"Failed to send floor number to elevator: {e}")
        return f"error: {e}", None

    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_uploaded_audio(file: UploadFile = File(...)):
    temp_filename = None
    try:
        allowed_exts = {'.m4a', '.mp3', '.wav', '.mpeg', '.mpga', '.ogg', '.webm'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_exts:
            logger.error(f"Unsupported file extension: {ext}")
            raise HTTPException(status_code=400, detail=f"Unsupported file extension: {ext}")

        # Save uploaded audio to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            audio_bytes = await file.read()
            temp_file.write(audio_bytes)
            temp_filename = temp_file.name
        logger.info(f"Saved uploaded audio to temp file: {temp_filename}")

        # Step 1: Transcribe audio with Groq Whisper model
        with open(temp_filename, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(temp_filename), f.read()),
                model="whisper-large-v3",
                language="en",
                response_format="json",
            )
        transcribed_text = transcription.text.strip()
        logger.info(f"Transcription result: {transcribed_text}")

        # Step 2: Extract floor number using Groq LLaMA chat completions (streaming)
        prompt = (
            "You are an assistant that extracts floor numbers from text. "
            "Reply only with the floor number as a single digit or 'none' if no number is present.\n"
            f"Text: \"{transcribed_text}\"\n"
            "Return only the number or 'none'."
        )

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts floor numbers."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_completion_tokens=10,
            top_p=1,
            stream=True,
        )

        extracted_text = ""
        for chunk in completion:
            delta = getattr(chunk.choices[0], "delta", None)
            if delta and getattr(delta, "content", None):
                extracted_text += delta.content
                logger.debug(f"Streaming chunk: {delta.content}")

        floor_number_raw = extracted_text.strip().lower()
        logger.info(f"Raw floor extraction output: {floor_number_raw}")

        if floor_number_raw in ("none", ""):
            floor_number = None
        else:
            try:
                floor_number = int(floor_number_raw)
            except ValueError:
                floor_number = None

        logger.info(f"Final extracted floor number: {floor_number}")

        tcp_status = None
        elevator_reply = None
        if floor_number is not None:
            tcp_status, elevator_reply = await send_floor_to_elevator_async(floor_number)
            logger.info(f"TCP send status: {tcp_status} ; elevator_reply: {elevator_reply}")

        return TranscribeResponse(
            transcription=transcribed_text,
            floor_number=floor_number,
            message=f"Extracted floor number: {floor_number if floor_number is not None else 'None'}",
            tcp_status=tcp_status,
            elevator_reply=elevator_reply,
        )

    except Exception as e:
        logger.exception(f"Error in /transcribe: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing audio: {str(e)}")

    finally:
        # Cleanup temp file
        if temp_filename and os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
                logger.info(f"Deleted temp file: {temp_filename}")
            except Exception as e:
                logger.error(f"Failed to delete temp file: {e}")
