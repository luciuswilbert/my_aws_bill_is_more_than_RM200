import os
import uuid
import boto3
import time
import json
import argparse
from pathlib import Path
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from dotenv import load_dotenv

# Load .env (contains AWS creds + bucket name + region)
load_dotenv()

# --- Constants ---
FIXED_JOB_ID = "d8a9b1c0-d2e3-4f56-a7b8-c9d0e1f2a3b4"  # Fixed UUID for predictable output
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

# --- AWS Clients ---
s3 = boto3.client("s3", region_name=REGION)
transcribe = boto3.client("transcribe", region_name=REGION)
polly = boto3.client("polly", region_name=REGION)
bedrock_runtime = boto3.client('bedrock-runtime', region_name=REGION)

# -------------------------------
# Utils (adapted from app.py)
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
            print("...Transcription COMPLETED.")
            return status
        elif status == "FAILED":
            raise Exception("Transcription failed")
        
        print("...Transcription in progress...")
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


def synthesize_speech(text: str, output_path: Path, target_lang: str, format="mp3"):
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
    with open(output_path, "wb") as f:
        f.write(response["AudioStream"].read())
    return str(output_path)


def combine_video_audio(video_path: str, audio_path: str, output_path: str):
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)
    final = video.with_audio(audio)
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")
    return output_path


def run_localization_pipeline(video_file: str, target_lang: str, force_transcribe: bool, force_translate: bool, force_analysis: bool, force_synthesize: bool, force_merge: bool):
    """
    Executes the full video localization pipeline for a single file.
    """
    # --- Setup ---
    video_path = Path(video_file)
    if not video_path.exists():
        print(f"Error: Video file not found at '{video_file}'")
        return

    job_id = FIXED_JOB_ID
    output_dir = Path("output") / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Using output directory: {output_dir}\n")

    # --- Define paths for intermediate files ---
    transcript_path = output_dir / "transcript.txt"
    translated_path = output_dir / "translated.txt"
    analysis_path = output_dir / "translation_analysis.json"
    audio_path = output_dir / "synthesized_audio.mp3"
    output_video_path = output_dir / f"localized_{video_path.name}"

    # --- Step 2: Transcribe ---
    if not transcript_path.exists() or force_transcribe:
        print("Step 1 & 2: Uploading and Transcribing video...")
        s3_key = f"videos/{job_id}_{video_path.name}"
        s3_uri = upload_to_s3(str(video_path), s3_key)
        print(f"...Upload complete. S3 URI: {s3_uri}")

        job_name = f"job_{job_id}"
        start_transcription_job(s3_uri, job_name)
        wait_for_transcription(job_name)
        transcript = get_transcript_text(job_name, output_dir)
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript)
        print("...Transcription saved.")
    else:
        print("Step 1 & 2: Skipping transcription (file exists).")
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = f.read()
    print(f"--- Original Transcript ---\n{transcript}\n-------------------------\n")

    # --- Step 3: Translate ---
    if not translated_path.exists() or force_translate:
        print("Step 3: Translating text...")
        translated_text = translate_text(transcript, target_lang)
        if translated_text:
            with open(translated_path, "w", encoding="utf-8") as f:
                f.write(translated_text)
            print("...Translation saved.")
        else:
            print("...Translation failed. Exiting.")
            return
    else:
        print("Step 3: Skipping translation (file exists).")
        with open(translated_path, "r", encoding="utf-8") as f:
            translated_text = f.read()
    print(f"--- Translated Text ({target_lang}) ---\n{translated_text}\n---------------------------\n")

    # --- Step 3.5: Analyze Translation Quality ---
    analysis_result = None
    if not analysis_path.exists() or force_analysis:
        print("Step 3.5: Analyzing translation quality...")
        analysis_result = analyze_translation_quality(transcript, translated_text)
        if analysis_result:
            with open(analysis_path, "w", encoding="utf-8") as f:
                json.dump(analysis_result, f, indent=2)
            print("...Analysis saved.")
        else:
            print("...Analysis failed.")
    else:
        print("Step 3.5: Skipping translation analysis (file exists).")
        with open(analysis_path, "r", encoding="utf-8") as f:
            analysis_result = json.load(f)

    print("--- Translation Analysis ---")
    print(f"{json.dumps(analysis_result, indent=2)}\n---------------------------\n")

    # --- Step 4: Synthesize Speech (TTS) ---
    if not audio_path.exists() or force_synthesize:
        print("Step 4: Synthesizing new audio...")
        synthesize_speech(translated_text, audio_path, target_lang)
        print(f"...New audio saved to: {audio_path}\n")
    else:
        print(f"Step 4: Skipping audio synthesis (file exists at {audio_path}).\n")

    # --- Step 5: Merge Video and Audio ---
    if not output_video_path.exists() or force_merge:
        print("Step 5: Combining original video with new audio...")
        combine_video_audio(str(video_path), str(audio_path), str(output_video_path))
        print(f"...Final video saved locally to: {output_video_path}\n")
    else:
        print(f"Step 5: Skipping video merge (file exists at {output_video_path}).\n")

    # --- Step 6: Upload Final Video ---
    output_key = f"localized/{job_id}_localized.mp4"
    final_s3_uri = f"s3://{BUCKET}/{output_key}"

    if not force_merge and not force_synthesize and not force_translate and not force_transcribe:
        print("Step 6: Skipping final S3 upload as no new video was generated.")
        # You might want to construct the final S3 URI here anyway if you need it.
    else:
        print("Step 6: Uploading final video to S3...")
        upload_to_s3(str(output_video_path), output_key)
        print(f"...Upload complete.\n")

    print("=" * 40)
    print("Localization process finished successfully!")
    print("\n--- Final Result ---")
    print(f"Final Video S3 URI: {final_s3_uri}")
    if analysis_result and analysis_result.get("potential_issues"):
        print("\nTranslation Quality Analysis:")
        print(json.dumps(analysis_result, indent=2))
    print("=" * 40)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Localize a video using AWS Transcribe, Translate, and Polly."
    )
    parser.add_argument(
        "video_file", 
        type=str, 
        help="Path to the local video file to be localized."
    )
    parser.add_argument(
        "target_language", 
        type=str, 
        help="Target language code for translation (e.g., 'es', 'fr', 'ja')."
    )
    parser.add_argument('--force-transcribe', action='store_true', help="Force re-running the transcription step.")
    parser.add_argument('--force-translate', action='store_true', help="Force re-running the translation step.")
    parser.add_argument('--force-analysis', action='store_true', help="Force re-running the translation analysis step.")
    parser.add_argument('--force-synthesize', action='store_true', help="Force re-running the audio synthesis step.")
    parser.add_argument('--force-merge', action='store_true', help="Force re-running the video merge step.")
    args = parser.parse_args()

    run_localization_pipeline(args.video_file, args.target_language, args.force_transcribe, args.force_translate, args.force_analysis, args.force_synthesize, args.force_merge)
