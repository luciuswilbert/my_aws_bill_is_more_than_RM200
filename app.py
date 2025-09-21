import os
import uuid
import boto3
import time
import json
import shutil
import tempfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, Form, BackgroundTasks, HTTPException, status
from dotenv import load_dotenv
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.audio.io.AudioFileClip import AudioFileClip

# Load .env (contains AWS creds + bucket name + region)
load_dotenv()

REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
BUCKET = os.getenv("S3_BUCKET_NAME", "video-bucket-ken")

# --- Polly Voice Configuration ---
# Maps language codes to Polly voices with preferred engines.
VOICE_MAP = {
    "zh-HK": {"id": "Hiujin", "engine": "neural"},      # Chinese (Cantonese)
    "zh-CN": {"id": "Zhiyu", "engine": "neural"},      # Chinese (Mandarin)
    "zh":    {"id": "Zhiyu", "engine": "neural"},      # Default for Chinese
    "en-US": {"id": "Danielle", "engine": "generative"}, # English (US)
    "en":    {"id": "Danielle", "engine": "generative"}, # Default for English
    "es-US": {"id": "Lupe", "engine": "generative"},      # Spanish (US)
    "es":    {"id": "Lupe", "engine": "generative"},      # Default for Spanish
}
DEFAULT_VOICE = VOICE_MAP["en"]  # Default to English (US)

s3 = boto3.client("s3", region_name=REGION)
transcribe = boto3.client("transcribe", region_name=REGION)
polly = boto3.client("polly", region_name=REGION)
bedrock_runtime = boto3.client('bedrock-runtime', region_name=REGION)

app = FastAPI()
TEMP_DIR = Path(tempfile.gettempdir())

# A simple in-memory dictionary to store job statuses and results.
# In a production environment, use a more persistent store like Redis or a database.
JOB_STATUSES = {}



# -------------------------------
# Utils
# -------------------------------
def upload_to_s3(local_path: str, s3_key: str):
    s3.upload_file(local_path, BUCKET, s3_key)
    return f"s3://{BUCKET}/{s3_key}"


def download_from_s3(s3_key: str, local_path: str):
    s3.download_file(BUCKET, s3_key, local_path)
    return local_path


def start_transcription_job(s3_uri: str, job_name: str):
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": s3_uri},
        MediaFormat="mp4",
        IdentifyLanguage=True,
        OutputBucketName=BUCKET,
        OutputKey=f"transcripts/{job_name}.json"
    )


def wait_for_transcription(job_name: str):
    while True:
        status = transcribe.get_transcription_job(
            TranscriptionJobName=job_name
        )["TranscriptionJob"]["TranscriptionJobStatus"]

        if status == "COMPLETED":
            return status
        elif status == "FAILED":
            raise Exception("Transcription failed")
        time.sleep(10)


def get_transcript_text(job_name: str, temp_dir: Path):
    key = f"transcripts/{job_name}.json"
    local_json = temp_dir / f"{job_name}.json"

    download_from_s3(key, str(local_json))

    with open(local_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data["results"]["transcripts"][0]["transcript"]


def translate_text(text: str, target_lang: str, model_id='us.amazon.nova-pro-v1:0'):
    """
    Translates text using Amazon Bedrock with the Nova Pro model.
    """
    try:
        # System prompt to guide the model for translation
        system_prompt = f"You are an expert translator. Translate the following text to {target_lang}. Your response should only contain the translated text, with no additional explanations, introductions, or conversational text."
        system_list = [{"text": system_prompt}]

        # User message with the text to translate
        message_list = [
            {
                "role": "user",
                "content": [{"text": text}]
            }
        ]

        # Inference parameters for translation
        inference_config = {
            "maxTokens": 4096,
            "temperature": 0.1, # Lower temperature for more deterministic and accurate translation
            "topP": 0.9
        }

        # Full request payload for Bedrock
        native_request = {
            "schemaVersion": "messages-v1",
            "system": system_list,
            "messages": message_list,
            "inferenceConfig": inference_config
        }

        # Invoke Nova Pro model via Bedrock
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps(native_request),
            contentType='application/json',
            accept='application/json'
        )

        response_body = json.loads(response['body'].read())
        translated_text = response_body["output"]["message"]["content"][0]["text"]
        return translated_text

    except Exception as e:
        print(f"Error translating text with Bedrock: {e}")
        return None


def analyze_translation_quality(original_text: str, translated_text: str, model_id='us.amazon.nova-pro-v1:0'):
    """
    Compares original and translated text to find potential translation errors using Bedrock.
    """
    try:
        system_prompt = """You are an expert linguistic analyst. Your task is to compare an original text with its translation and identify phrases that may have been translated incorrectly, focusing on these categories: Idioms & Proverbs, Fixed Expressions / Colloquialisms, Cultural References, and Puns & Wordplay.

Return ONLY a single JSON object with one key, "potential_issues", which contains a list of objects. Each object in the list must have these fields:
- "original_phrase": The phrase from the original text.
- "translated_phrase": The corresponding phrase in the translated text.
- "category": One of "Idiom/Proverb", "Colloquialism", "Cultural Reference", or "Puns/Wordplay".
- "explanation": A brief explanation of why this might be a mistranslation.

If no issues are found, return an empty list for the "potential_issues" key. Do not add any text outside the JSON object.
Example of a valid response:
{"potential_issues": [{"original_phrase": "it's raining cats and dogs", "translated_phrase": "está lloviendo gatos y perros", "category": "Idiom/Proverb", "explanation": "This is a literal translation of an English idiom. A more natural translation would be 'está lloviendo a cántaros'."}]}"""

        user_prompt = f"""Original Text:
---
{original_text}
---

Translated Text:
---
{translated_text}
---"""

        system_list = [{"text": system_prompt}]
        message_list = [{"role": "user", "content": [{"text": user_prompt}]}]

        inference_config = {"maxTokens": 4096, "temperature": 0.1, "topP": 0.9}

        native_request = {
            "schemaVersion": "messages-v1",
            "system": system_list,
            "messages": message_list,
            "inferenceConfig": inference_config,
        }

        response = bedrock_runtime.invoke_model(
            modelId=model_id, body=json.dumps(native_request)
        )

        response_body = json.loads(response["body"].read())
        analysis_text = response_body["output"]["message"]["content"][0]["text"]

        # Clean potential markdown code block
        if analysis_text.strip().startswith("```json"):
            analysis_text = analysis_text.strip()[7:-3].strip()
        return json.loads(analysis_text)
    except Exception as e:
        print(f"Error analyzing translation quality with Bedrock: {e}")
        return {"error": str(e), "potential_issues": []}


def synthesize_speech(text: str, temp_dir: Path, target_lang: str, format="mp3"):
    voice_config = VOICE_MAP.get(target_lang, DEFAULT_VOICE)
    voice_id = voice_config["id"]
    engine = voice_config["engine"]

    print(f"...Using voice: {voice_id} ({engine} engine) for language: {target_lang}")

    response = polly.synthesize_speech(
        Text=text,
        OutputFormat=format,
        VoiceId=voice_id,
        Engine=engine
    )
    audio_path = temp_dir / f"{uuid.uuid4()}.mp3"
    with open(audio_path, "wb") as f:
        f.write(response["AudioStream"].read())
    return str(audio_path)


def combine_video_audio(video_path: str, audio_path: str, output_path: str):
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)
    final = video.with_audio(audio)
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")
    return output_path

def run_localization_task(temp_dir: Path, local_video_path: Path, video_id: str, target_lang: str):
    """
    This function runs the entire long-running localization process in the background.
    """
    try:
        # Step 1: Upload video to S3
        JOB_STATUSES[video_id] = {"status": "in_progress", "step": "1/6: Uploading video"}
        print(f"[{video_id}] Step 1: Uploading video to S3...")
        s3_key = f"videos/{video_id}_{local_video_path.name}"
        s3_uri = upload_to_s3(str(local_video_path), s3_key)
        print(f"[{video_id}] ...Upload complete.")

        # Step 2: Transcribe
        JOB_STATUSES[video_id]["step"] = "2/6: Transcribing video"
        print(f"[{video_id}] Step 2: Starting transcription...")
        job_name = f"job_{video_id}"
        start_transcription_job(s3_uri, job_name)
        wait_for_transcription(job_name)
        transcript = get_transcript_text(job_name, temp_dir)
        print(f"[{video_id}] ...Transcription complete.")

        # Step 3: Translate
        JOB_STATUSES[video_id]["step"] = "3/6: Translating text"
        print(f"[{video_id}] Step 3: Translating text...")
        translated_text = translate_text(transcript, target_lang)
        print(f"[{video_id}] ...Translation complete.")

        # Step 3.5: Analyze Translation Quality
        JOB_STATUSES[video_id]["step"] = "3.5/6: Analyzing translation quality"
        print(f"[{video_id}] Step 3.5: Analyzing translation quality...")
        analysis_result = analyze_translation_quality(transcript, translated_text)
        print(f"[{video_id}] ...Analysis complete.")

        # Step 4: Synthesize Speech (TTS)
        JOB_STATUSES[video_id]["step"] = "4/6: Synthesizing audio"
        print(f"[{video_id}] Step 4: Synthesizing new audio...")
        audio_path = synthesize_speech(translated_text, temp_dir, target_lang)
        print(f"[{video_id}] ...Audio synthesis complete.")

        # Step 5: Merge
        JOB_STATUSES[video_id]["step"] = "5/6: Merging video and audio"
        print(f"[{video_id}] Step 5: Merging video and audio...")
        output_path = temp_dir / f"{video_id}_localized.mp4"
        combine_video_audio(str(local_video_path), audio_path, str(output_path))
        print(f"[{video_id}] ...Merge complete.")

        # Step 6: Upload result to S3
        JOB_STATUSES[video_id]["step"] = "6/6: Uploading final video"
        print(f"[{video_id}] Step 6: Uploading final video...")
        output_key = f"localized/{video_id}_localized.mp4"
        upload_to_s3(str(output_path), output_key)
        print(f"[{video_id}] ...Final upload complete.")

        # Prepare the final result
        final_result = {
            "video_uri": f"s3://{BUCKET}/{output_key}",
            "transcript": transcript,
            "translation": translated_text,
            "translation_analysis": analysis_result
        }
        # Update the job status to "completed" with the final result
        JOB_STATUSES[video_id] = {"status": "completed", "result": final_result}
        print(f"[{video_id}] JOB COMPLETE. Result: {json.dumps(final_result, indent=2)}")

    except Exception as e:
        print(f"[{video_id}] An error occurred during localization: {e}")
        # Update the job status to "failed" with the error message
        JOB_STATUSES[video_id] = {"status": "failed", "error": str(e)}
    finally:
        # Clean up the temporary directory to prevent disk space issues
        print(f"[{video_id}] Cleaning up temporary directory: {temp_dir}")
        shutil.rmtree(temp_dir)


# -------------------------------
# API Endpoints
# -------------------------------
@app.post("/localize")
async def localize_video(background_tasks: BackgroundTasks, file: UploadFile, target_lang: str = Form(...)):
    # --- Setup ---
    video_id = str(uuid.uuid4())
    temp_dir = TEMP_DIR / video_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    local_video_path = temp_dir / file.filename
    with open(local_video_path, "wb") as f:  # Save uploaded file locally
        f.write(await file.read())

    # Initialize the job status
    JOB_STATUSES[video_id] = {"status": "starting"}

    # Add the long-running task to the background
    background_tasks.add_task(run_localization_task, temp_dir, local_video_path, video_id, target_lang)

    # Immediately return a response to the client
    return {
        "message": "Localization job started.",
        "video_id": video_id,
        "status_url": f"/localize/status/{video_id}"
    }

@app.get("/localize/status/{video_id}")
async def get_localization_status(video_id: str):
    status_info = JOB_STATUSES.get(video_id)
    if not status_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job ID not found.")
    return status_info
